"""Unit tests for integration prompt builders."""

from __future__ import annotations

import json
from uuid import uuid4

from fetch.application.integrations.context import IntegrationContext
from fetch.application.integrations.prompt import (
    INTEGRATION_PROMPT_VERSION,
    build_integration_system_prompt,
    build_integration_user_message,
)
from fetch.domain.entities import ApiOperation, AuthScheme
from fetch.domain.enums import AuthSchemeType, GenerationLanguage, HttpMethod

_REVISION_ID = uuid4()
_WORKSPACE_ID = uuid4()


def _make_operation(method: str = "POST", path: str = "/v1/orders") -> ApiOperation:
    return ApiOperation(
        id=uuid4(),
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        method=HttpMethod(method),
        path=path,
        path_normalized=path.lower(),
        operation_id=None,
        summary="Create order",
        description=None,
        tags=[],
        deprecated=False,
        logical_key=f"src:1.0:{method}:{path.lower()}",
        source_pointer=None,
        security_requirements=[],
    )


def _make_context(
    operation: ApiOperation | None = None,
    auth_schemes: list[AuthScheme] | None = None,
    request_schema_json: str | None = None,
) -> IntegrationContext:
    if operation is None:
        operation = _make_operation()
    return IntegrationContext(
        operation=operation,
        base_url="https://api.example.com",
        auth_schemes=auth_schemes or [],
        parameters=[],
        request_body=None,
        request_schema_json=request_schema_json,
        response_schemas=[],
        examples=[],
        error_definitions=[],
        api_title="Test API",
    )


class TestIntegrationPromptVersion:
    def test_version_is_v1(self) -> None:
        assert INTEGRATION_PROMPT_VERSION == "v1"


class TestSystemPrompt:
    def test_contains_injection_safety(self) -> None:
        prompt = build_integration_system_prompt(GenerationLanguage.PYTHON)
        assert "INJECTION SAFETY" in prompt

    def test_contains_language_name_python(self) -> None:
        prompt = build_integration_system_prompt(GenerationLanguage.PYTHON)
        assert "python" in prompt.lower()

    def test_contains_language_name_typescript(self) -> None:
        prompt = build_integration_system_prompt(GenerationLanguage.TYPESCRIPT)
        assert "typescript" in prompt.lower()

    def test_contains_language_name_java(self) -> None:
        prompt = build_integration_system_prompt(GenerationLanguage.JAVA)
        assert "java" in prompt.lower()

    def test_requires_env_vars_for_credentials(self) -> None:
        prompt = build_integration_system_prompt(GenerationLanguage.PYTHON)
        assert "environment variable" in prompt.lower()


class TestUserMessage:
    def test_contains_method_and_path(self) -> None:
        ctx = _make_context(_make_operation("GET", "/v1/items"))
        msg = build_integration_user_message(ctx, GenerationLanguage.PYTHON)
        assert "GET" in msg
        assert "/v1/items" in msg

    def test_contains_auth_scheme_info(self) -> None:
        scheme = AuthScheme(
            id=uuid4(),
            revision_id=_REVISION_ID,
            workspace_id=_WORKSPACE_ID,
            name="bearerAuth",
            scheme_type=AuthSchemeType.HTTP,
            description=None,
            details_json=json.dumps({"scheme": "bearer"}),
        )
        ctx = _make_context(auth_schemes=[scheme])
        msg = build_integration_user_message(ctx, GenerationLanguage.PYTHON)
        assert "bearerAuth" in msg

    def test_contains_required_field_from_schema(self) -> None:
        schema = json.dumps(
            {
                "type": "object",
                "required": ["customer_id"],
                "properties": {"customer_id": {"type": "string"}},
            }
        )
        ctx = _make_context(request_schema_json=schema)
        msg = build_integration_user_message(ctx, GenerationLanguage.PYTHON)
        assert "customer_id" in msg

    def test_no_auth_message_when_no_schemes(self) -> None:
        ctx = _make_context(auth_schemes=[])
        msg = build_integration_user_message(ctx, GenerationLanguage.PYTHON)
        assert "No authentication required" in msg
