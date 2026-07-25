from __future__ import annotations

import json
import re

from fetch.domain.entities import (
    ApiOperation,
    AuthScheme,
    DiagnosticFinding,
    ParsedRequest,
)
from fetch.domain.enums import DiagnosticCategory

_REAL_TOKEN_RE = re.compile(r"Bearer\s+[A-Za-z0-9+/._\-]{30,}")


def _parse_auth_scheme_details(scheme: AuthScheme) -> dict[str, str]:
    """Parse details_json to extract sub-fields for validators."""
    try:
        return json.loads(scheme.details_json) if scheme.details_json else {}
    except (json.JSONDecodeError, TypeError):
        return {}


class HeaderValidator:
    def validate(
        self,
        parsed: ParsedRequest,
        operation: ApiOperation,
        auth_schemes: list[AuthScheme],
    ) -> list[DiagnosticFinding]:
        findings: list[DiagnosticFinding] = []
        auth_lower = (parsed.auth_header or "").lower()

        for scheme in auth_schemes:
            scheme_type = str(scheme.scheme_type).lower()
            details = _parse_auth_scheme_details(scheme)
            http_scheme = str(details.get("scheme", "")).lower()
            api_key_in = str(details.get("in", "")).lower()
            api_key_name = str(details.get("name", "")).lower()

            if scheme_type in ("http", "oauth2", "openidconnect"):
                if http_scheme == "bearer" or scheme_type in (
                    "oauth2",
                    "openidconnect",
                ):
                    if "authorization" not in parsed.headers:
                        findings.append(
                            DiagnosticFinding(
                                severity="error",
                                category=DiagnosticCategory.AUTH,
                                message="Authorization header is missing. Bearer authentication is required.",
                                field="Authorization",
                            )
                        )
                    elif not auth_lower.startswith("bearer "):
                        findings.append(
                            DiagnosticFinding(
                                severity="error",
                                category=DiagnosticCategory.AUTH,
                                message="Authorization header must use Bearer scheme.",
                                field="Authorization",
                                canonical_value="Bearer <YOUR_API_KEY>",
                            )
                        )
                elif http_scheme == "basic":
                    if "authorization" not in parsed.headers:
                        findings.append(
                            DiagnosticFinding(
                                severity="error",
                                category=DiagnosticCategory.AUTH,
                                message="Authorization header is missing. Basic authentication is required.",
                                field="Authorization",
                            )
                        )
                    elif not auth_lower.startswith("basic "):
                        findings.append(
                            DiagnosticFinding(
                                severity="error",
                                category=DiagnosticCategory.AUTH,
                                message="Authorization header must use Basic scheme.",
                                field="Authorization",
                                canonical_value="Basic <base64(user:pass)>",
                            )
                        )
            elif scheme_type == "apikey" and api_key_in == "header":
                if api_key_name and api_key_name not in parsed.headers:
                    findings.append(
                        DiagnosticFinding(
                            severity="error",
                            category=DiagnosticCategory.AUTH,
                            message=f"Required API key header '{api_key_name}' is missing.",
                            field=api_key_name,
                        )
                    )

        # Content-Type check
        has_body_schema = getattr(operation, "request_body", None) is not None
        if has_body_schema and parsed.body_raw:
            request_body = getattr(operation, "request_body", None)
            if request_body is not None:
                content_schemas = getattr(request_body, "content_schemas", {}) or {}
                if content_schemas and parsed.content_type not in content_schemas:
                    findings.append(
                        DiagnosticFinding(
                            severity="error",
                            category=DiagnosticCategory.HEADER,
                            message=(
                                f"Content-Type '{parsed.content_type}' does not match "
                                f"expected: {', '.join(content_schemas.keys())}"
                            ),
                            field="Content-Type",
                            canonical_value=next(iter(content_schemas.keys()), None),
                        )
                    )

        # Real token warning — only check if auth_header is present
        if parsed.auth_header and _REAL_TOKEN_RE.search(parsed.auth_header):
            findings.append(
                DiagnosticFinding(
                    severity="warning",
                    category=DiagnosticCategory.AUTH,
                    message="Authorization header appears to contain a real credential. Use environment variables.",
                    field="Authorization",
                )
            )

        return findings


class ParameterValidator:
    def validate(
        self,
        parsed: ParsedRequest,
        operation: ApiOperation,
        path_params: dict[str, str],
    ) -> list[DiagnosticFinding]:
        findings: list[DiagnosticFinding] = []
        parameters = getattr(operation, "parameters", []) or []

        for param in parameters:
            location = str(getattr(param, "location", "") or "").lower()
            name = str(getattr(param, "name", "") or "")
            required = bool(getattr(param, "required", False))
            deprecated = bool(getattr(param, "deprecated", False))
            schema_json_str = getattr(param, "schema_json", None)

            if location == "path":
                value = path_params.get(name)
                if value is None:
                    findings.append(
                        DiagnosticFinding(
                            severity="error",
                            category=DiagnosticCategory.PARAMETER,
                            message=f"Required path parameter '{name}' is missing.",
                            field=f"path.{name}",
                        )
                    )
                    continue
            elif location == "query":
                value = parsed.query_params.get(name)
                if value is None:
                    if required:
                        findings.append(
                            DiagnosticFinding(
                                severity="error",
                                category=DiagnosticCategory.PARAMETER,
                                message=f"Required query parameter '{name}' is missing.",
                                field=f"query.{name}",
                            )
                        )
                    continue
            elif location == "header":
                value = parsed.headers.get(name.lower())
                if value is None and required:
                    findings.append(
                        DiagnosticFinding(
                            severity="error",
                            category=DiagnosticCategory.PARAMETER,
                            message=f"Required header parameter '{name}' is missing.",
                            field=name,
                        )
                    )
                    continue
            else:
                continue

            if deprecated and value is not None:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        category=DiagnosticCategory.PARAMETER,
                        message=f"Parameter '{name}' is deprecated.",
                        field=name,
                    )
                )

            if value is not None and schema_json_str:
                try:
                    schema = json.loads(schema_json_str)
                    param_type = schema.get("type", "")
                    enum_values = schema.get("enum")

                    if param_type == "integer":
                        try:
                            int(value)
                        except (ValueError, TypeError):
                            findings.append(
                                DiagnosticFinding(
                                    severity="error",
                                    category=DiagnosticCategory.PARAMETER,
                                    message=f"Parameter '{name}' must be an integer, got '{value}'.",
                                    field=name,
                                    canonical_value="integer",
                                )
                            )
                    elif param_type == "boolean":
                        if value.lower() not in ("true", "false"):
                            findings.append(
                                DiagnosticFinding(
                                    severity="error",
                                    category=DiagnosticCategory.PARAMETER,
                                    message=f"Parameter '{name}' must be 'true' or 'false', got '{value}'.",
                                    field=name,
                                )
                            )
                    elif param_type == "number":
                        try:
                            float(value)
                        except (ValueError, TypeError):
                            findings.append(
                                DiagnosticFinding(
                                    severity="error",
                                    category=DiagnosticCategory.PARAMETER,
                                    message=f"Parameter '{name}' must be a number, got '{value}'.",
                                    field=name,
                                )
                            )

                    if enum_values and value not in enum_values:
                        findings.append(
                            DiagnosticFinding(
                                severity="error",
                                category=DiagnosticCategory.PARAMETER,
                                message=f"Parameter '{name}' must be one of: {enum_values}. Got '{value}'.",
                                field=name,
                                canonical_value=str(enum_values),
                            )
                        )
                except (json.JSONDecodeError, TypeError):
                    pass

        return findings


class BodyValidator:
    def validate(
        self,
        parsed: ParsedRequest,
        operation: ApiOperation,
    ) -> list[DiagnosticFinding]:
        import jsonschema

        findings: list[DiagnosticFinding] = []
        request_body = getattr(operation, "request_body", None)
        required_body = (
            getattr(request_body, "required", False) if request_body else False
        )

        if request_body is None:
            if parsed.body_raw:
                findings.append(
                    DiagnosticFinding(
                        severity="warning",
                        category=DiagnosticCategory.BODY,
                        message="Operation does not expect a request body.",
                        field=None,
                    )
                )
            return findings

        if required_body and not parsed.body_raw:
            findings.append(
                DiagnosticFinding(
                    severity="error",
                    category=DiagnosticCategory.BODY,
                    message="Required request body is missing.",
                    field=None,
                )
            )
            return findings

        if parsed.is_url_encoded_body:
            content_schemas = getattr(request_body, "content_schemas", {}) or {}
            if "application/json" in content_schemas:
                findings.append(
                    DiagnosticFinding(
                        severity="error",
                        category=DiagnosticCategory.BODY,
                        message="Request body should be JSON (application/json), not URL-encoded.",
                        field="Content-Type",
                        canonical_value="application/json",
                    )
                )
            return findings

        if parsed.body_json is None:
            return findings

        content_schemas = getattr(request_body, "content_schemas", {}) or {}
        schema_json_str = content_schemas.get("application/json")
        if not schema_json_str:
            return findings

        try:
            schema = json.loads(schema_json_str)
        except (json.JSONDecodeError, TypeError):
            return findings

        validator = jsonschema.Draft7Validator(schema)
        for error in validator.iter_errors(parsed.body_json):
            path = (
                ".".join(str(p) for p in error.absolute_path)
                if error.absolute_path
                else None
            )
            field = f"body.{path}" if path else "body"
            severity = (
                "warning" if "additionalProperties" in str(error.validator) else "error"
            )
            findings.append(
                DiagnosticFinding(
                    severity=severity,
                    category=DiagnosticCategory.BODY,
                    message=error.message,
                    field=field,
                )
            )

        return findings
