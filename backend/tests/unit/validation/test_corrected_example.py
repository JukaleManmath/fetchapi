"""Tests for build_corrected_curl."""

from __future__ import annotations

import json
from uuid import uuid4

from fetch.application.validation.corrected_example import build_corrected_curl
from fetch.domain.entities import (
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    AuthScheme,
    ParsedRequest,
)
from fetch.domain.enums import AuthSchemeType, HttpMethod, ParameterLocation


def _make_op(
    method: str = "GET",
    path: str = "/v1/items",
    parameters: list | None = None,
    request_body: ApiRequestBody | None = None,
) -> ApiOperation:
    return ApiOperation(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        method=HttpMethod(method.upper()),
        path=path,
        path_normalized=path.lower(),
        operation_id=None,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key=f"test:{method.upper()}:{path}",
        source_pointer=None,
        parameters=parameters or [],
        request_body=request_body,
        responses=[],
        security_requirements=[],
    )


def _make_parsed(
    query_params: dict | None = None, body_json: dict | None = None
) -> ParsedRequest:
    return ParsedRequest(
        method="GET",
        url="https://api.example.com/v1/items",
        headers={},
        body_raw=None,
        body_json=body_json,
        content_type=None,
        auth_header=None,
        query_params=query_params or {},
        is_url_encoded_body=False,
    )


def _make_bearer_scheme() -> AuthScheme:
    return AuthScheme(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        name="bearerAuth",
        scheme_type=AuthSchemeType.HTTP,
        description=None,
        details_json=json.dumps({"scheme": "bearer"}),
    )


def _make_apikey_scheme(name: str = "X-API-Key") -> AuthScheme:
    return AuthScheme(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        name="apiKeyAuth",
        scheme_type=AuthSchemeType.API_KEY,
        description=None,
        details_json=json.dumps({"in": "header", "name": name}),
    )


def test_get_with_bearer_scheme_contains_auth_header() -> None:
    op = _make_op("GET", "/v1/items")
    scheme = _make_bearer_scheme()
    result = build_corrected_curl(
        op, "https://api.example.com", [scheme], _make_parsed()
    )
    assert "Authorization: Bearer <YOUR_API_KEY>" in result


def test_post_with_required_fields_has_body_scaffold() -> None:
    schema = {"type": "object", "required": ["name", "email"], "properties": {}}
    rb = ApiRequestBody(
        id=uuid4(),
        operation_id=uuid4(),
        required=True,
        description=None,
        content_schemas={"application/json": json.dumps(schema)},
    )
    op = _make_op("POST", "/v1/users", request_body=rb)
    result = build_corrected_curl(op, "https://api.example.com", [], _make_parsed())
    assert "name" in result
    assert "email" in result


def test_path_param_filled_from_query_params_or_placeholder() -> None:
    param = ApiParameter(
        id=uuid4(),
        revision_id=uuid4(),
        operation_id=uuid4(),
        name="id",
        location=ParameterLocation.PATH,
        required=True,
        deprecated=False,
        description=None,
        schema_json=None,
        example_json=None,
        source_pointer=None,
    )
    op = _make_op("GET", "/v1/items/{id}", parameters=[param])
    result = build_corrected_curl(op, "https://api.example.com", [], _make_parsed())
    assert "<id>" in result


def test_api_key_header_scheme_uses_correct_header_name() -> None:
    op = _make_op("GET", "/v1/items")
    scheme = _make_apikey_scheme("X-My-Token")
    result = build_corrected_curl(
        op, "https://api.example.com", [scheme], _make_parsed()
    )
    assert "X-My-Token: <YOUR_API_KEY>" in result
