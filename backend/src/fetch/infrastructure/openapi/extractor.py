"""Canonical entity extraction from a resolved OpenAPI document.

Takes the output of validator.load_and_resolve() and returns domain entities.

Rules enforced:
- OpenAPI 3.1 type normalization: ["string", "null"] → type=string, nullable=true
- Schema property recursion capped at MAX_SCHEMA_DEPTH (5 levels)
- Path normalization: strip trailing slash, lowercase, preserve {params}
- Logical key derivation: {source_id}:{api_version}:{METHOD}:{path_normalized}
- Cycle detection via seen-set during schema extraction
"""

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from fetch.infrastructure.openapi.validator import _resolve_pointer

from fetch.domain.entities import (
    ApiExample,
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    ApiResponse,
    ApiSchema,
    ApiServer,
    AuthScheme,
    ErrorDefinition,
)
from fetch.domain.enums import AuthSchemeType, HttpMethod, ParameterLocation

logger = logging.getLogger(__name__)

MAX_SCHEMA_DEPTH = 5

_HTTP_METHODS = {m.value.lower() for m in HttpMethod}

_DOC_ROOT: dict[str, Any] = {}  # module-level ref to current doc; set per extraction batch


def _deref(node: Any, root: dict[str, Any], seen: set[str]) -> Any:
    """Follow a $ref one level and return the target, or return node as-is.

    Only follows internal (#/...) refs.  Never recurses deeper — callers
    must call _deref again if they need to follow further refs.
    Cycle guard via `seen` set of ref strings.
    """
    if not isinstance(node, dict) or "$ref" not in node:
        return node
    ref: str = node["$ref"]
    if not ref.startswith("#") or ref in seen:
        return node
    try:
        return _resolve_pointer(root, ref[1:])
    except (KeyError, IndexError, ValueError):
        return node


# ── Path normalization ─────────────────────────────────────────────────────────


def normalize_path(path: str) -> str:
    """Strip trailing slash and lowercase the path, preserving {param} names.

    Examples:
        /v1/Customers/  → /v1/customers
        /v1/{Id}/items  → /v1/{id}/items  ← Note: params ARE lowercased per CLAUDE.md §11.4
    """
    # Lowercase the whole path, then restore param names as written
    # ARCHITECTURE.md §11.4: "preserve path parameter names as-is"
    # We lowercase the static segments only.
    path = path.rstrip("/") or "/"
    segments = path.split("/")
    normalized = []
    for seg in segments:
        if seg.startswith("{") and seg.endswith("}"):
            normalized.append(seg)  # preserve param names exactly
        else:
            normalized.append(seg.lower())
    return "/".join(normalized)


# ── OpenAPI 3.1 type normalization ─────────────────────────────────────────────


def normalize_schema_types(schema: dict[str, Any]) -> dict[str, Any]:
    """Normalize OpenAPI 3.1 array types in-place.

    ["string", "null"] → type="string", nullable=true
    """
    if not isinstance(schema, dict):
        return schema
    raw_type = schema.get("type")
    if isinstance(raw_type, list):
        non_null = [t for t in raw_type if t != "null"]
        has_null = "null" in raw_type
        schema = dict(schema)
        schema["type"] = non_null[0] if len(non_null) == 1 else non_null
        if has_null:
            schema["nullable"] = True
    return schema


# ── Schema extraction with depth + cycle guard ─────────────────────────────────


def _schema_to_dict(
    node: Any,
    root: dict[str, Any],
    depth: int,
    seen_refs: set[str],
) -> Any:
    """Recursively serialize a schema node to a plain JSON-safe dict.

    - Follows $ref strings on demand (never materializes shared object graphs).
    - Caps recursion at MAX_SCHEMA_DEPTH.
    - Breaks $ref cycles via seen_refs.
    - Works on the original unresolved doc — no cyclic Python object graphs.
    """
    if depth > MAX_SCHEMA_DEPTH:
        return {"$ref": "#/depth-limit-reached"}

    if isinstance(node, dict):
        if "$ref" in node:
            ref: str = node["$ref"]
            if not ref.startswith("#") or ref in seen_refs:
                return {"$ref": ref}
            try:
                target = _resolve_pointer(root, ref[1:])
            except (KeyError, IndexError, ValueError):
                return {"$ref": ref}
            return _schema_to_dict(target, root, depth + 1, seen_refs | {ref})
        result = {}
        for k, v in node.items():
            result[k] = _schema_to_dict(v, root, depth + 1, seen_refs)
        return result
    if isinstance(node, list):
        return [_schema_to_dict(item, root, depth + 1, seen_refs) for item in node]
    return node


def extract_schema_json(
    schema: dict[str, Any],
    root: dict[str, Any] | None = None,
    pointer: str = "",
    depth: int = 0,
    seen_pointers: set[str] | None = None,
    memo: dict[int, Any] | None = None,
) -> str:
    """Serialize a schema node to a JSON string.

    Works on the original unresolved document — follows $ref strings lazily
    rather than materializing a cyclic resolved object graph.
    """
    if root is None:
        root = {}
    if seen_pointers is None:
        seen_pointers = set()

    if pointer and pointer in seen_pointers:
        return json.dumps({"$ref": pointer})
    if depth > MAX_SCHEMA_DEPTH:
        return json.dumps({"$ref": pointer or "#/depth-limit-reached"})

    safe = _schema_to_dict(schema, root, 0, {pointer} if pointer else set())
    safe = normalize_schema_types(safe) if isinstance(safe, dict) else safe
    return json.dumps(safe, default=str)


# ── Server extraction ──────────────────────────────────────────────────────────


def extract_servers(
    doc: dict[str, Any],
    revision_id: UUID,
) -> list[ApiServer]:
    servers = []
    for raw in doc.get("servers", [{"url": "/"}]):
        if not isinstance(raw, dict):
            continue
        servers.append(
            ApiServer(
                id=uuid4(),
                revision_id=revision_id,
                url=raw.get("url", "/"),
                description=raw.get("description"),
                variables=raw.get("variables", {}),
            )
        )
    return servers


# ── Auth scheme extraction ─────────────────────────────────────────────────────


def extract_auth_schemes(
    doc: dict[str, Any],
    revision_id: UUID,
    workspace_id: UUID,
) -> list[AuthScheme]:
    schemes: list[AuthScheme] = []
    security_schemes = doc.get("components", {}).get("securitySchemes", {})
    if not isinstance(security_schemes, dict):
        return schemes

    for name, raw in security_schemes.items():
        if not isinstance(raw, dict):
            continue
        raw_type = raw.get("type", "")
        try:
            scheme_type = AuthSchemeType(raw_type)
        except ValueError:
            scheme_type = AuthSchemeType.HTTP  # fallback

        schemes.append(
            AuthScheme(
                id=uuid4(),
                revision_id=revision_id,
                workspace_id=workspace_id,
                name=name,
                scheme_type=scheme_type,
                description=raw.get("description"),
                details_json=json.dumps(
                    {k: v for k, v in raw.items() if k not in ("type", "description")},
                    default=str,
                ),
            )
        )
    return schemes


# ── Schema extraction ──────────────────────────────────────────────────────────


def extract_schemas(
    doc: dict[str, Any],
    revision_id: UUID,
    workspace_id: UUID,
    source_id: UUID,
    api_version: str,
) -> list[ApiSchema]:
    schemas: list[ApiSchema] = []
    component_schemas = doc.get("components", {}).get("schemas", {})
    if not isinstance(component_schemas, dict):
        return schemas

    for name, raw in component_schemas.items():
        if not isinstance(raw, dict):
            continue
        pointer = f"#/components/schemas/{name}"
        normalized = normalize_schema_types(raw)
        nullable = bool(normalized.get("nullable", False))
        deprecated = bool(raw.get("deprecated", False))
        logical_key = f"{source_id}:{api_version}:{pointer}"

        schemas.append(
            ApiSchema(
                id=uuid4(),
                revision_id=revision_id,
                workspace_id=workspace_id,
                name=name,
                description=raw.get("description"),
                schema_json=extract_schema_json(raw, root=doc, pointer=pointer),
                source_pointer=pointer,
                logical_key=logical_key,
                nullable=nullable,
                deprecated=deprecated,
            )
        )
    return schemas


# ── Operation extraction ───────────────────────────────────────────────────────


def _extract_parameters(
    raw_params: list[Any],
    revision_id: UUID,
    operation_uuid: UUID,
    root: dict[str, Any],
) -> list[ApiParameter]:
    params = []
    for raw in raw_params:
        if not isinstance(raw, dict):
            continue
        # Follow a top-level $ref on the parameter object itself
        raw = _deref(raw, root, set())
        if not isinstance(raw, dict):
            continue
        location_str = raw.get("in", "query")
        try:
            location = ParameterLocation(location_str)
        except ValueError:
            location = ParameterLocation.QUERY

        schema_raw = raw.get("schema")
        params.append(
            ApiParameter(
                id=uuid4(),
                revision_id=revision_id,
                operation_id=operation_uuid,
                name=raw.get("name", ""),
                location=location,
                required=bool(raw.get("required", False)),
                deprecated=bool(raw.get("deprecated", False)),
                description=raw.get("description"),
                schema_json=extract_schema_json(schema_raw, root=root) if schema_raw else None,
                example_json=json.dumps(raw["example"], default=str)
                if "example" in raw
                else None,
                source_pointer=raw.get("x-source-pointer"),
            )
        )
    return params


def _extract_content_schemas(content: Any, root: dict[str, Any]) -> dict[str, str]:
    """Map content-type → serialized JSON Schema string."""
    if not isinstance(content, dict):
        return {}
    result = {}
    for media_type, media_obj in content.items():
        if isinstance(media_obj, dict) and "schema" in media_obj:
            result[media_type] = extract_schema_json(media_obj["schema"], root=root)
    return result


def _extract_request_body(
    raw_body: dict[str, Any],
    operation_uuid: UUID,
    root: dict[str, Any],
) -> ApiRequestBody:
    return ApiRequestBody(
        id=uuid4(),
        operation_id=operation_uuid,
        required=bool(raw_body.get("required", False)),
        description=raw_body.get("description"),
        content_schemas=_extract_content_schemas(raw_body.get("content", {}), root),
    )


def _extract_responses(
    raw_responses: dict[str, Any],
    operation_uuid: UUID,
    root: dict[str, Any],
) -> list[ApiResponse]:
    responses = []
    if not isinstance(raw_responses, dict):
        return responses
    for status_code, raw_resp in raw_responses.items():
        if not isinstance(raw_resp, dict):
            continue
        raw_resp = _deref(raw_resp, root, set())
        if not isinstance(raw_resp, dict):
            continue
        raw_headers = raw_resp.get("headers", {})
        headers = {
            name: str(hobj.get("description", ""))
            for name, hobj in raw_headers.items()
            if isinstance(hobj, dict)
        }
        responses.append(
            ApiResponse(
                id=uuid4(),
                operation_id=operation_uuid,
                status_code=str(status_code),
                description=raw_resp.get("description"),
                content_schemas=_extract_content_schemas(raw_resp.get("content", {}), root),
                headers=headers,
            )
        )
    return responses


def extract_operations(
    doc: dict[str, Any],
    revision_id: UUID,
    workspace_id: UUID,
    source_id: UUID,
    api_version: str,
) -> list[ApiOperation]:
    operations: list[ApiOperation] = []
    paths = doc.get("paths", {})
    if not isinstance(paths, dict):
        return operations

    for raw_path, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue
        path_normalized = normalize_path(raw_path)

        # Path-level parameters shared across all methods
        path_level_params: list[Any] = path_item.get("parameters", [])

        for method_str, operation_raw in path_item.items():
            if method_str.lower() not in _HTTP_METHODS:
                continue
            if not isinstance(operation_raw, dict):
                continue

            try:
                method = HttpMethod(method_str.upper())
            except ValueError:
                continue

            op_id = uuid4()
            logical_key = f"{source_id}:{api_version}:{method.value}:{path_normalized}"
            pointer = f"#/paths/{raw_path.replace('/', '~1')}/{method_str}"

            # Merge path-level params with operation-level (operation wins on name+in)
            op_params_raw: list[Any] = operation_raw.get("parameters", [])
            all_params_raw = _merge_parameters(path_level_params, op_params_raw)

            parameters = _extract_parameters(all_params_raw, revision_id, op_id, doc)

            request_body = None
            if "requestBody" in operation_raw:
                request_body = _extract_request_body(
                    operation_raw["requestBody"], op_id, doc
                )

            responses = _extract_responses(operation_raw.get("responses", {}), op_id, doc)

            operations.append(
                ApiOperation(
                    id=op_id,
                    revision_id=revision_id,
                    workspace_id=workspace_id,
                    method=method,
                    path=raw_path,
                    path_normalized=path_normalized,
                    operation_id=operation_raw.get("operationId"),
                    summary=operation_raw.get("summary"),
                    description=operation_raw.get("description"),
                    tags=operation_raw.get("tags", []),
                    deprecated=bool(operation_raw.get("deprecated", False)),
                    logical_key=logical_key,
                    source_pointer=pointer,
                    parameters=parameters,
                    request_body=request_body,
                    responses=responses,
                    security_requirements=operation_raw.get("security", []),
                )
            )
    return operations


def _merge_parameters(path_level: list[Any], op_level: list[Any]) -> list[Any]:
    """Operation-level parameters override path-level ones on (name, in)."""
    merged: dict[tuple[str, str], Any] = {}
    for p in path_level:
        if isinstance(p, dict):
            merged[(p.get("name", ""), p.get("in", ""))] = p
    for p in op_level:
        if isinstance(p, dict):
            merged[(p.get("name", ""), p.get("in", ""))] = p
    return list(merged.values())


# ── Example extraction ─────────────────────────────────────────────────────────


def extract_examples(
    doc: dict[str, Any],
    revision_id: UUID,
    workspace_id: UUID,
) -> list[ApiExample]:
    """Extract named examples from components/examples."""
    examples: list[ApiExample] = []
    component_examples = doc.get("components", {}).get("examples", {})
    if not isinstance(component_examples, dict):
        return examples

    for name, raw in component_examples.items():
        if not isinstance(raw, dict):
            continue
        value = raw.get("value") or raw.get("externalValue")
        if value is None:
            continue
        examples.append(
            ApiExample(
                id=uuid4(),
                revision_id=revision_id,
                workspace_id=workspace_id,
                operation_id=None,
                title=raw.get("summary") or name,
                description=raw.get("description"),
                language=None,
                content=json.dumps(value, default=str)
                if not isinstance(value, str)
                else value,
                source_pointer=f"#/components/examples/{name}",
            )
        )
    return examples


# ── Error definition extraction ────────────────────────────────────────────────


def extract_error_definitions(
    operations: list[ApiOperation],
    revision_id: UUID,
    workspace_id: UUID,
) -> list[ErrorDefinition]:
    """Derive error definitions from 4xx/5xx responses on extracted operations."""
    errors = []
    for op in operations:
        for resp in op.responses:
            code = resp.status_code
            if not (code.startswith("4") or code.startswith("5") or code == "default"):
                continue
            errors.append(
                ErrorDefinition(
                    id=uuid4(),
                    revision_id=revision_id,
                    workspace_id=workspace_id,
                    operation_id=op.id,
                    status_code=code if code != "default" else None,
                    error_code=None,
                    title=resp.description,
                    description=resp.description,
                    source_pointer=op.source_pointer,
                )
            )
    return errors


# ── Top-level extraction entry point ──────────────────────────────────────────


def extract_api_version(doc: dict[str, Any]) -> str:
    """Extract the API info.version string, defaulting to '0.0.0'."""
    return str(doc.get("info", {}).get("version", "0.0.0"))


def extract_api_title(doc: dict[str, Any]) -> str:
    """Extract the API info.title string."""
    return str(doc.get("info", {}).get("title", "Untitled API"))
