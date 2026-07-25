from __future__ import annotations

import json

from fetch.application.validation.validators import _parse_auth_scheme_details
from fetch.domain.entities import ApiOperation, AuthScheme, ParsedRequest


def build_corrected_curl(
    operation: ApiOperation,
    base_url: str,
    auth_schemes: list[AuthScheme],
    parsed: ParsedRequest,
) -> str:
    lines: list[str] = []
    method = operation.method.upper()

    # Build URL with path params substituted
    path = operation.path
    parameters = getattr(operation, "parameters", []) or []
    for param in parameters:
        if str(getattr(param, "location", "")).lower() == "path":
            name = getattr(param, "name", "")
            value = parsed.query_params.get(name) or f"<{name}>"
            path = path.replace(f"{{{name}}}", value)

    url = f"{base_url.rstrip('/')}{path}"

    if method != "GET":
        lines.append(f"curl -X {method} {url!r} \\")
    else:
        lines.append(f"curl {url!r} \\")

    # Auth headers
    for scheme in auth_schemes:
        scheme_type = str(scheme.scheme_type).lower()
        details = _parse_auth_scheme_details(scheme)
        http_scheme = str(details.get("scheme", "")).lower()
        api_key_in = str(details.get("in", "")).lower()
        api_key_name = str(details.get("name", ""))

        if scheme_type in ("http", "oauth2", "openidconnect"):
            if http_scheme in ("bearer", "") or scheme_type in (
                "oauth2",
                "openidconnect",
            ):
                lines.append('  -H "Authorization: Bearer <YOUR_API_KEY>" \\')
            elif http_scheme == "basic":
                lines.append('  -H "Authorization: Basic <YOUR_CREDENTIALS>" \\')
        elif scheme_type == "apikey" and api_key_in == "header" and api_key_name:
            lines.append(f'  -H "{api_key_name}: <YOUR_API_KEY>" \\')

    # Content-Type if JSON body expected
    request_body = getattr(operation, "request_body", None)
    if request_body is not None:
        content_schemas = getattr(request_body, "content_schemas", {}) or {}
        if "application/json" in content_schemas:
            lines.append('  -H "Content-Type: application/json" \\')

    # Required header params
    for param in parameters:
        if str(getattr(param, "location", "")).lower() == "header" and getattr(
            param, "required", False
        ):
            name = getattr(param, "name", "")
            lines.append(f'  -H "{name}: <{name}>" \\')

    # Body
    if request_body is not None:
        content_schemas = getattr(request_body, "content_schemas", {}) or {}
        schema_json_str = content_schemas.get("application/json")
        if schema_json_str:
            if parsed.body_json:
                body = json.dumps(parsed.body_json)
            else:
                # Build minimal scaffold from required fields
                try:
                    schema = json.loads(schema_json_str)
                    required_fields = schema.get("required", [])
                    scaffold = {f: f"<{f}>" for f in required_fields}
                except Exception:
                    scaffold = {}
                body = json.dumps(scaffold) if scaffold else '{"<field>": "<value>"}'
            lines.append(f"  -d {body!r} \\")

    # Remove trailing backslash from last line
    if lines:
        lines[-1] = lines[-1].rstrip(" \\")

    return "\n".join(lines)
