"""OpenAPI document validation and $ref resolution.

Responsibilities:
- Safe YAML loading (yaml.safe_load only)
- YAML alias expansion limit (prevents billion-laughs DoS)
- OpenAPI 3.0.x / 3.1.x version detection and validation
- Internal $ref resolution with cycle detection
- External $ref fetching with SSRF protection, hop limit, size limit, timeout
- Source pointer preservation before dereferencing

External ref protections (from config):
  EXT_REF_MAX_HOPS   — max chained external hops (default 3)
  EXT_REF_MAX_BYTES  — max bytes per external fetch (default 1 MB)
  EXT_REF_TIMEOUT_SECONDS — connect+read timeout (default 10 s)

SSRF blocked ranges: loopback, private, link-local, multicast, cloud metadata.
"""

import ipaddress
import json
import logging
import re
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import yaml
from openapi_spec_validator import OpenAPIV30SpecValidator, OpenAPIV31SpecValidator
from openapi_spec_validator.readers import read_from_filename

from fetch.config import get_settings
from fetch.domain.errors import IngestionError

logger = logging.getLogger(__name__)

# IP ranges blocked for SSRF protection
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("10.0.0.0/8"),        # private
    ipaddress.ip_network("172.16.0.0/12"),     # private
    ipaddress.ip_network("192.168.0.0/16"),    # private
    ipaddress.ip_network("169.254.0.0/16"),    # link-local (AWS metadata etc.)
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
    ipaddress.ip_network("224.0.0.0/4"),       # multicast
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("0.0.0.0/8"),         # "this" network
    ipaddress.ip_network("100.64.0.0/10"),     # shared address space
]

_ALLOWED_SCHEMES = {"http", "https"}


def _is_ssrf_blocked(url: str) -> bool:
    """Return True if the URL resolves to a blocked IP range."""
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        return True
    hostname = parsed.hostname
    if not hostname:
        return True
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return True
    for info in infos:
        addr = info[4][0]
        try:
            ip = ipaddress.ip_address(addr)
        except ValueError:
            return True
        for network in _BLOCKED_NETWORKS:
            if ip in network:
                return True
    return False


def _count_aliases_in_node(node: Any, seen: set[int] | None = None) -> int:
    """Count alias expansions in a composed YAML node tree.

    After yaml.compose(), aliases are represented as the same node object
    appearing multiple times in the tree. Track by object id to detect them.
    """
    if node is None:
        return 0
    if seen is None:
        seen = set()
    nid = id(node)
    if nid in seen:
        return 1  # Same node reachable again — this is an alias expansion
    seen.add(nid)
    count = 0
    if isinstance(node, yaml.MappingNode):
        for key_node, val_node in node.value:
            count += _count_aliases_in_node(key_node, seen)
            count += _count_aliases_in_node(val_node, seen)
    elif isinstance(node, yaml.SequenceNode):
        for child in node.value:
            count += _count_aliases_in_node(child, seen)
    return count


_DEFAULT_MAX_ALIASES = 100


def load_yaml_safe(content: bytes | str, max_aliases: int = _DEFAULT_MAX_ALIASES) -> dict[str, Any]:
    """Parse YAML or JSON content safely.

    Raises IngestionError on:
    - Parse failure
    - Alias count exceeding max_aliases
    - Non-dict root
    """

    text = content.decode() if isinstance(content, bytes) else content

    # Try JSON first (faster and unambiguous)
    if text.lstrip().startswith("{"):
        try:
            doc = json.loads(text)
        except json.JSONDecodeError as exc:
            raise IngestionError(f"JSON parse error: {exc}") from exc
        if not isinstance(doc, dict):
            raise IngestionError("OpenAPI document root must be a mapping, not a scalar or list.")
        return doc  # type: ignore[return-value]

    # YAML path: compose first to count aliases before construction
    try:
        composed = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise IngestionError(f"YAML parse error: {exc}") from exc

    alias_count = _count_aliases_in_node(composed)
    if alias_count > max_aliases:
        raise IngestionError(
            f"YAML alias count {alias_count} exceeds limit {max_aliases}. "
            "Aborting to prevent alias-expansion DoS."
        )

    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise IngestionError(f"YAML parse error: {exc}") from exc

    if not isinstance(doc, dict):
        raise IngestionError("OpenAPI document root must be a mapping, not a scalar or list.")

    return doc  # type: ignore[return-value]


def detect_openapi_version(doc: dict[str, Any]) -> str:
    """Return '3.0' or '3.1'. Raises IngestionError for unsupported versions."""
    raw = doc.get("openapi") or doc.get("swagger", "")
    if not raw or not isinstance(raw, str):
        raise IngestionError("Missing or non-string 'openapi' field.")
    if raw.startswith("3.1"):
        return "3.1"
    if raw.startswith("3.0"):
        return "3.0"
    raise IngestionError(
        f"Unsupported OpenAPI version '{raw}'. Only 3.0.x and 3.1.x are supported."
    )


def validate_openapi(doc: dict[str, Any], version: str) -> None:
    """Run openapi-spec-validator. Raises IngestionError on validation failure."""
    try:
        if version == "3.1":
            OpenAPIV31SpecValidator(doc).validate()
        else:
            OpenAPIV30SpecValidator(doc).validate()
    except Exception as exc:
        raise IngestionError(f"OpenAPI validation failed: {exc}") from exc


async def fetch_external_ref(
    url: str,
    *,
    max_bytes: int,
    timeout: float,
) -> dict[str, Any]:
    """Fetch an external $ref URL with SSRF protection and size limit.

    Raises IngestionError on SSRF block, timeout, size limit, or non-dict result.
    """
    if _is_ssrf_blocked(url):
        raise IngestionError(f"External $ref URL blocked by SSRF policy: {url}")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                chunks: list[bytes] = []
                total = 0
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    total += len(chunk)
                    if total > max_bytes:
                        raise IngestionError(
                            f"External $ref {url} exceeds size limit {max_bytes} bytes."
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
    except httpx.TimeoutException as exc:
        raise IngestionError(f"External $ref {url} timed out: {exc}") from exc
    except httpx.HTTPStatusError as exc:
        raise IngestionError(
            f"External $ref {url} returned HTTP {exc.response.status_code}."
        ) from exc

    # Validate redirect target too
    if _is_ssrf_blocked(str(response.url)):
        raise IngestionError(
            f"External $ref redirect target blocked by SSRF policy: {response.url}"
        )

    try:
        doc = load_yaml_safe(content)
    except IngestionError as exc:
        raise IngestionError(f"External $ref {url} parse error: {exc}") from exc

    return doc


def _resolve_pointer(doc: dict[str, Any], pointer: str) -> Any:
    """Resolve a JSON Pointer (RFC 6901) within a document."""
    if pointer == "" or pointer == "#":
        return doc
    parts = pointer.lstrip("#/").split("/")
    node: Any = doc
    for part in parts:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict):
            node = node[part]
        elif isinstance(node, list):
            node = node[int(part)]
        else:
            raise KeyError(f"Cannot traverse into {type(node)} at '{part}'")
    return node


class RefResolver:
    """Resolve $ref pointers in an OpenAPI document in-place.

    - Internal refs (#/components/...) are resolved recursively.
    - External refs are fetched once and cached.
    - Cycles are detected and broken — the $ref is left as-is (not dereferenced).
    - Alias/expansion limit is enforced at load time (load_yaml_safe).
    - Max external hops enforced per chain.
    """

    def __init__(
        self,
        root: dict[str, Any],
        base_url: str | None = None,
        max_hops: int = 3,
        max_bytes: int = 1_048_576,
        timeout: float = 10.0,
    ) -> None:
        self._root = root
        self._base_url = base_url
        self._max_hops = max_hops
        self._max_bytes = max_bytes
        self._timeout = timeout
        # Maps $ref string → resolved node (prevents re-fetching)
        self._external_cache: dict[str, dict[str, Any]] = {}
        # Tracks refs currently on the call stack for cycle detection
        self._resolving: set[str] = set()

    def resolve(self) -> dict[str, Any]:
        """Return a fully resolved copy of the root document."""
        return self._resolve_node(self._root, hops=0)  # type: ignore[return-value]

    def _resolve_node(self, node: Any, hops: int) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return self._resolve_ref(node["$ref"], hops)
            return {k: self._resolve_node(v, hops) for k, v in node.items()}
        if isinstance(node, list):
            return [self._resolve_node(item, hops) for item in node]
        return node

    def _resolve_ref(self, ref: str, hops: int) -> Any:
        # Cycle detection
        if ref in self._resolving:
            logger.debug("openapi_ref_cycle_detected", extra={"ref": ref})
            return {"$ref": ref}  # leave as-is

        if ref.startswith("#"):
            # Internal reference
            self._resolving.add(ref)
            try:
                pointer = ref[1:]  # strip leading '#'
                target = _resolve_pointer(self._root, pointer)
                return self._resolve_node(target, hops)
            except (KeyError, IndexError, ValueError) as exc:
                raise IngestionError(f"Cannot resolve internal $ref '{ref}': {exc}") from exc
            finally:
                self._resolving.discard(ref)
        else:
            # External reference
            return self._resolve_external_ref_sync(ref, hops)

    def _resolve_external_ref_sync(self, ref: str, hops: int) -> Any:
        """Synchronous wrapper — external refs must be resolved before calling resolve()
        via resolve_external_refs_async(), or this will raise."""
        if ref in self._external_cache:
            fragment = ""
            url_part = ref
            if "#" in ref:
                url_part, fragment = ref.split("#", 1)
            ext_doc = self._external_cache[url_part]
            target = _resolve_pointer(ext_doc, fragment) if fragment else ext_doc
            self._resolving.add(ref)
            try:
                return self._resolve_node(target, hops)
            finally:
                self._resolving.discard(ref)
        # If not pre-cached, leave as-is (caller should use async resolve)
        logger.debug("openapi_external_ref_not_cached", extra={"ref": ref})
        return {"$ref": ref}

    async def _fetch_and_cache(self, url: str, hops: int) -> None:
        if url in self._external_cache:
            return
        if hops >= self._max_hops:
            raise IngestionError(
                f"External $ref chain exceeds max hops ({self._max_hops}): {url}"
            )
        doc = await fetch_external_ref(
            url, max_bytes=self._max_bytes, timeout=self._timeout
        )
        self._external_cache[url] = doc

    async def prefetch_external_refs(self, node: Any = None, hops: int = 0) -> None:
        """Walk the document and pre-fetch all external $refs before synchronous resolution."""
        if node is None:
            node = self._root
        if isinstance(node, dict):
            if "$ref" in node:
                ref: str = node["$ref"]
                if not ref.startswith("#"):
                    url_part = ref.split("#")[0]
                    absolute = (
                        urljoin(self._base_url, url_part) if self._base_url else url_part
                    )
                    await self._fetch_and_cache(absolute, hops)
                    # Recurse into the fetched doc to find nested external refs
                    await self.prefetch_external_refs(
                        self._external_cache.get(absolute, {}), hops + 1
                    )
            else:
                for v in node.values():
                    await self.prefetch_external_refs(v, hops)
        elif isinstance(node, list):
            for item in node:
                await self.prefetch_external_refs(item, hops)


async def load_and_resolve(
    content: bytes,
    source_url: str | None = None,
    max_aliases: int = _DEFAULT_MAX_ALIASES,
) -> tuple[dict[str, Any], str]:
    """Full pipeline: load → validate → resolve refs.

    Returns (resolved_doc, openapi_version).
    Raises IngestionError on any failure.
    """
    doc = load_yaml_safe(content, max_aliases=max_aliases)
    version = detect_openapi_version(doc)
    validate_openapi(doc, version)

    resolver = RefResolver(doc, base_url=source_url)
    await resolver.prefetch_external_refs()
    resolved = resolver.resolve()

    return resolved, version
