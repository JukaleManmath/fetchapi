from __future__ import annotations

import re
import urllib.parse

from fetch.domain.entities import ApiOperation, ApiServer, EndpointMatch
from fetch.domain.enums import MatchConfidence


class EndpointMatcher:
    def __init__(
        self, operations: list[ApiOperation], servers: list[ApiServer]
    ) -> None:
        self._operations = operations
        self._server_urls = [s.url.rstrip("/") for s in servers if s.url]
        # Pre-compile path template regexes
        self._path_regexes: dict[str, re.Pattern[str]] = {}
        for op in operations:
            pattern = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", op.path)
            self._path_regexes[str(op.id)] = re.compile(f"^{pattern}$")

    def match(self, method: str, url: str) -> EndpointMatch:
        method_upper = method.upper()
        path = self._extract_path(url)

        # Step 1: exact match
        for op in self._operations:
            if op.method.upper() != method_upper:
                continue
            op_path = getattr(op, "path_normalized", op.path).rstrip("/") or op.path
            if self._normalize_path(path) == self._normalize_path(op_path):
                return EndpointMatch(
                    operation=op,
                    path_params={},
                    match_confidence=MatchConfidence.EXACT,
                )

        # Step 2: path template match — prefer most specific (fewest path params)
        candidates: list[tuple[ApiOperation, dict[str, str], int]] = []
        for op in self._operations:
            if op.method.upper() != method_upper:
                continue
            pattern = self._path_regexes.get(str(op.id))
            if pattern is None:
                continue
            m = pattern.match(self._normalize_path(path))
            if m:
                path_params = m.groupdict()
                specificity = op.path.count("{")
                candidates.append((op, path_params, specificity))

        if candidates:
            candidates.sort(key=lambda x: x[2])
            best_op, best_params, _ = candidates[0]
            return EndpointMatch(
                operation=best_op,
                path_params=best_params,
                match_confidence=MatchConfidence.PATH_TEMPLATE,
            )

        return EndpointMatch(
            operation=None,
            path_params={},
            match_confidence=MatchConfidence.NO_MATCH,
        )

    def _extract_path(self, url: str) -> str:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path or "/"
        # Strip server base URL prefix
        for base in self._server_urls:
            base_parsed = urllib.parse.urlparse(base)
            if parsed.netloc == base_parsed.netloc and path.startswith(
                base_parsed.path
            ):
                path = path[len(base_parsed.path.rstrip("/")) :]
                break
        return path or "/"

    @staticmethod
    def _normalize_path(path: str) -> str:
        return "/" + path.strip("/")
