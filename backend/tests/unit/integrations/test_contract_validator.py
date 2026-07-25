"""Unit tests for ContractValidator."""

from __future__ import annotations

import json
from uuid import uuid4

from fetch.application.integrations.context import IntegrationContext
from fetch.application.integrations.contract_validator import ContractValidator
from fetch.domain.entities import (
    ApiOperation,
    ApiRequestBody,
    AuthScheme,
)
from fetch.domain.enums import AuthSchemeType, GenerationLanguage, HttpMethod

_REVISION_ID = uuid4()
_WORKSPACE_ID = uuid4()
_OP_ID = uuid4()


def _make_operation(method: str = "POST", path: str = "/v1/payments") -> ApiOperation:
    return ApiOperation(
        id=_OP_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        method=HttpMethod(method),
        path=path,
        path_normalized=path.lower(),
        operation_id=None,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key=f"src:1.0:{method}:{path.lower()}",
        source_pointer=None,
        security_requirements=[],
    )


def _make_bearer_scheme() -> AuthScheme:
    return AuthScheme(
        id=uuid4(),
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        name="bearerAuth",
        scheme_type=AuthSchemeType.HTTP,
        description=None,
        details_json=json.dumps({"scheme": "bearer"}),
    )


def _make_context(
    operation: ApiOperation | None = None,
    auth_schemes: list[AuthScheme] | None = None,
    request_body: ApiRequestBody | None = None,
    request_schema_json: str | None = None,
) -> IntegrationContext:
    if operation is None:
        operation = _make_operation()
    return IntegrationContext(
        operation=operation,
        base_url="https://api.example.com",
        auth_schemes=auth_schemes or [],
        parameters=[],
        request_body=request_body,
        request_schema_json=request_schema_json,
        response_schemas=[],
        examples=[],
        error_definitions=[],
        api_title="Test API",
    )


def _make_valid_code(
    method: str = "POST",
    path: str = "/v1/payments",
    include_auth: bool = False,
    extra_fields: list[str] | None = None,
) -> str:
    lines = [f"{method} {path}"]
    if include_auth:
        lines.append("Authorization: Bearer $TOKEN")
    if extra_fields:
        for f in extra_fields:
            lines.append(f'"{f}": "value"')
    return "\n".join(lines)


class TestContractValidator:
    def setup_method(self) -> None:
        self.validator = ContractValidator()

    def test_valid_code_no_issues(self) -> None:
        ctx = _make_context()
        code = _make_valid_code(method="POST", path="/v1/payments")
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        assert issues == []

    def test_missing_http_method(self) -> None:
        ctx = _make_context(_make_operation(method="POST", path="/v1/payments"))
        code = "GET /v1/payments"  # POST is missing
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        method_errors = [i for i in issues if i.field == "method"]
        assert len(method_errors) == 1
        assert method_errors[0].severity == "error"
        assert method_errors[0].category == "contract"

    def test_missing_path(self) -> None:
        ctx = _make_context(_make_operation(method="GET", path="/v1/customers"))
        code = "GET /v1/other"  # /v1/customers missing
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        path_errors = [i for i in issues if i.field == "path"]
        assert len(path_errors) == 1
        assert path_errors[0].severity == "error"

    def test_missing_required_body_field(self) -> None:
        schema = json.dumps(
            {
                "type": "object",
                "required": ["amount"],
                "properties": {"amount": {"type": "integer"}},
            }
        )
        ctx = _make_context(request_schema_json=schema)
        code = "POST /v1/payments\n# no amount field here"
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        field_errors = [i for i in issues if i.field == "body.amount"]
        assert len(field_errors) == 1
        assert field_errors[0].severity == "error"
        assert field_errors[0].category == "contract"

    def test_required_field_present_no_issue(self) -> None:
        schema = json.dumps(
            {
                "type": "object",
                "required": ["amount"],
                "properties": {"amount": {"type": "integer"}},
            }
        )
        ctx = _make_context(request_schema_json=schema)
        code = 'POST /v1/payments\n"amount": 100'
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        field_errors = [i for i in issues if i.field == "body.amount"]
        assert field_errors == []

    def test_real_bearer_token_warning(self) -> None:
        ctx = _make_context()
        code = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIn0.abc"
        code = f"POST /v1/payments\n{code}"
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        security_warnings = [
            i for i in issues if i.category == "security" and i.severity == "warning"
        ]
        assert len(security_warnings) == 1

    def test_bearer_auth_required_present(self) -> None:
        ctx = _make_context(auth_schemes=[_make_bearer_scheme()])
        code = "POST /v1/payments\nAuthorization: Bearer $TOKEN"
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        auth_errors = [i for i in issues if i.field == "Authorization header"]
        assert auth_errors == []

    def test_bearer_auth_required_missing(self) -> None:
        ctx = _make_context(auth_schemes=[_make_bearer_scheme()])
        code = "POST /v1/payments\n# no auth header"
        issues = self.validator.validate(code, ctx, GenerationLanguage.PYTHON)
        auth_errors = [i for i in issues if i.field == "Authorization header"]
        assert len(auth_errors) == 1
        assert auth_errors[0].severity == "error"
