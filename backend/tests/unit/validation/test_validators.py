"""Tests for HeaderValidator, ParameterValidator, BodyValidator."""

from __future__ import annotations

import json
from uuid import uuid4

from fetch.application.validation.validators import (
    BodyValidator,
    HeaderValidator,
    ParameterValidator,
)
from fetch.domain.entities import (
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    AuthScheme,
    ParsedRequest,
)
from fetch.domain.enums import (
    AuthSchemeType,
    DiagnosticCategory,
    HttpMethod,
    ParameterLocation,
)


def _make_op(**kwargs: object) -> ApiOperation:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "revision_id": uuid4(),
        "workspace_id": uuid4(),
        "method": HttpMethod.POST,
        "path": "/v1/items",
        "path_normalized": "/v1/items",
        "operation_id": None,
        "summary": None,
        "description": None,
        "tags": [],
        "deprecated": False,
        "logical_key": "test:POST:/v1/items",
        "source_pointer": None,
        "parameters": [],
        "request_body": None,
        "responses": [],
        "security_requirements": [],
    }
    defaults.update(kwargs)
    return ApiOperation(**defaults)  # type: ignore[arg-type]


def _make_parsed(
    method: str = "POST",
    url: str = "https://api.example.com/v1/items",
    headers: dict | None = None,
    body_raw: str | None = None,
    body_json: dict | None = None,
    content_type: str | None = None,
    auth_header: str | None = None,
    query_params: dict | None = None,
    is_url_encoded_body: bool = False,
) -> ParsedRequest:
    return ParsedRequest(
        method=method,
        url=url,
        headers=headers or {},
        body_raw=body_raw,
        body_json=body_json,
        content_type=content_type,
        auth_header=auth_header,
        query_params=query_params or {},
        is_url_encoded_body=is_url_encoded_body,
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


def _make_basic_scheme() -> AuthScheme:
    return AuthScheme(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        name="basicAuth",
        scheme_type=AuthSchemeType.HTTP,
        description=None,
        details_json=json.dumps({"scheme": "basic"}),
    )


def _make_apikey_scheme(header_name: str = "X-API-Key") -> AuthScheme:
    return AuthScheme(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        name="apiKeyAuth",
        scheme_type=AuthSchemeType.API_KEY,
        description=None,
        details_json=json.dumps({"in": "header", "name": header_name}),
    )


# ── HeaderValidator tests ──────────────────────────────────────────────────────


class TestHeaderValidator:
    def setup_method(self) -> None:
        self.validator = HeaderValidator()
        self.op = _make_op()

    def test_missing_bearer_auth_is_error(self) -> None:
        parsed = _make_parsed(headers={})
        scheme = _make_bearer_scheme()
        findings = self.validator.validate(parsed, self.op, [scheme])
        assert any(
            f.category == DiagnosticCategory.AUTH and f.severity == "error"
            for f in findings
        )

    def test_wrong_scheme_prefix_is_error(self) -> None:
        parsed = _make_parsed(
            headers={"authorization": "Token abc123"},
            auth_header="Token abc123",
        )
        scheme = _make_bearer_scheme()
        findings = self.validator.validate(parsed, self.op, [scheme])
        assert any(
            f.category == DiagnosticCategory.AUTH and f.severity == "error"
            for f in findings
        )

    def test_missing_api_key_header_is_error(self) -> None:
        parsed = _make_parsed(headers={})
        scheme = _make_apikey_scheme("X-API-Key")
        findings = self.validator.validate(parsed, self.op, [scheme])
        assert any(
            f.category == DiagnosticCategory.AUTH and f.severity == "error"
            for f in findings
        )

    def test_wrong_content_type_is_header_error(self) -> None:
        rb = ApiRequestBody(
            id=uuid4(),
            operation_id=uuid4(),
            required=True,
            description=None,
            content_schemas={"application/json": "{}"},
        )
        op = _make_op(request_body=rb)
        parsed = _make_parsed(
            headers={"content-type": "text/plain"},
            body_raw="hello",
            content_type="text/plain",
        )
        findings = self.validator.validate(parsed, op, [])
        assert any(
            f.category == DiagnosticCategory.HEADER and f.severity == "error"
            for f in findings
        )

    def test_real_token_warning(self) -> None:
        token = "Bearer " + "A" * 40
        parsed = _make_parsed(
            headers={"authorization": token.lower()},
            auth_header=token,
        )
        scheme = _make_bearer_scheme()
        findings = self.validator.validate(parsed, self.op, [scheme])
        assert any(
            f.category == DiagnosticCategory.AUTH and f.severity == "warning"
            for f in findings
        )

    def test_valid_bearer_no_findings(self) -> None:
        parsed = _make_parsed(
            headers={"authorization": "bearer tok123"},
            auth_header="bearer tok123",
        )
        scheme = _make_bearer_scheme()
        findings = self.validator.validate(parsed, self.op, [scheme])
        auth_errors = [
            f
            for f in findings
            if f.category == DiagnosticCategory.AUTH and f.severity == "error"
        ]
        assert len(auth_errors) == 0


# ── ParameterValidator tests ───────────────────────────────────────────────────


class TestParameterValidator:
    def setup_method(self) -> None:
        self.validator = ParameterValidator()

    def _make_param(
        self,
        name: str,
        location: ParameterLocation,
        required: bool = False,
        deprecated: bool = False,
        schema_json: str | None = None,
    ) -> ApiParameter:
        return ApiParameter(
            id=uuid4(),
            revision_id=uuid4(),
            operation_id=uuid4(),
            name=name,
            location=location,
            required=required,
            deprecated=deprecated,
            description=None,
            schema_json=schema_json,
            example_json=None,
            source_pointer=None,
        )

    def test_missing_required_query_param_is_error(self) -> None:
        param = self._make_param("page", ParameterLocation.QUERY, required=True)
        op = _make_op(parameters=[param])
        parsed = _make_parsed(query_params={})
        findings = self.validator.validate(parsed, op, {})
        assert any(
            f.category == DiagnosticCategory.PARAMETER and f.severity == "error"
            for f in findings
        )

    def test_integer_type_error(self) -> None:
        param = self._make_param(
            "count",
            ParameterLocation.QUERY,
            schema_json=json.dumps({"type": "integer"}),
        )
        op = _make_op(parameters=[param])
        parsed = _make_parsed(query_params={"count": "notanint"})
        findings = self.validator.validate(parsed, op, {})
        assert any(
            f.category == DiagnosticCategory.PARAMETER and f.severity == "error"
            for f in findings
        )

    def test_enum_violation_has_canonical_value(self) -> None:
        param = self._make_param(
            "status",
            ParameterLocation.QUERY,
            schema_json=json.dumps({"type": "string", "enum": ["active", "inactive"]}),
        )
        op = _make_op(parameters=[param])
        parsed = _make_parsed(query_params={"status": "pending"})
        findings = self.validator.validate(parsed, op, {})
        errors = [
            f
            for f in findings
            if f.category == DiagnosticCategory.PARAMETER and f.severity == "error"
        ]
        assert errors
        assert errors[0].canonical_value is not None

    def test_deprecated_param_warning(self) -> None:
        param = self._make_param("old_field", ParameterLocation.QUERY, deprecated=True)
        op = _make_op(parameters=[param])
        parsed = _make_parsed(query_params={"old_field": "value"})
        findings = self.validator.validate(parsed, op, {})
        assert any(
            f.category == DiagnosticCategory.PARAMETER and f.severity == "warning"
            for f in findings
        )


# ── BodyValidator tests ────────────────────────────────────────────────────────


class TestBodyValidator:
    def setup_method(self) -> None:
        self.validator = BodyValidator()

    def _make_json_body_op(
        self, schema: dict | None = None, required: bool = True
    ) -> ApiOperation:
        schema_str = json.dumps(schema) if schema else "{}"
        rb = ApiRequestBody(
            id=uuid4(),
            operation_id=uuid4(),
            required=required,
            description=None,
            content_schemas={"application/json": schema_str},
        )
        return _make_op(request_body=rb)

    def test_missing_required_body_is_error(self) -> None:
        op = self._make_json_body_op(required=True)
        parsed = _make_parsed(body_raw=None, body_json=None)
        findings = self.validator.validate(parsed, op)
        assert any(
            f.category == DiagnosticCategory.BODY and f.severity == "error"
            for f in findings
        )

    def test_unexpected_body_is_warning(self) -> None:
        op = _make_op(request_body=None)
        parsed = _make_parsed(body_raw='{"foo":"bar"}')
        findings = self.validator.validate(parsed, op)
        assert any(
            f.category == DiagnosticCategory.BODY and f.severity == "warning"
            for f in findings
        )

    def test_missing_required_json_field_is_error(self) -> None:
        schema = {
            "type": "object",
            "required": ["name"],
            "properties": {"name": {"type": "string"}},
        }
        op = self._make_json_body_op(schema=schema)
        parsed = _make_parsed(body_json={}, body_raw="{}")
        findings = self.validator.validate(parsed, op)
        assert any(
            f.category == DiagnosticCategory.BODY and f.severity == "error"
            for f in findings
        )

    def test_type_violation_in_body_is_error(self) -> None:
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        op = self._make_json_body_op(schema=schema)
        parsed = _make_parsed(
            body_json={"count": "notanint"}, body_raw='{"count":"notanint"}'
        )
        findings = self.validator.validate(parsed, op)
        assert any(
            f.category == DiagnosticCategory.BODY and f.severity == "error"
            for f in findings
        )

    def test_url_encoded_body_when_json_expected(self) -> None:
        op = self._make_json_body_op()
        parsed = _make_parsed(
            body_raw="name=foo",
            content_type="application/x-www-form-urlencoded",
            is_url_encoded_body=True,
        )
        findings = self.validator.validate(parsed, op)
        assert any(
            f.category == DiagnosticCategory.BODY and f.severity == "error"
            for f in findings
        )
