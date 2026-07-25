from __future__ import annotations

from dataclasses import dataclass

from fetch.domain.entities import (
    ApiExample,
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    AuthScheme,
    ErrorDefinition,
)


@dataclass(frozen=True)
class IntegrationContext:
    """All context needed to generate integration code for one operation."""

    operation: ApiOperation
    base_url: str
    auth_schemes: list[AuthScheme]
    parameters: list[ApiParameter]
    request_body: ApiRequestBody | None
    request_schema_json: str | None  # "application/json" schema as JSON string
    response_schemas: list[tuple[str, str]]  # [(status_code, schema_json), ...]
    examples: list[ApiExample]
    error_definitions: list[ErrorDefinition]
    api_title: str | None
