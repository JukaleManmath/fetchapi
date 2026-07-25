"""Unit tests for IntegrationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from fetch.application.integrations.context import IntegrationContext
from fetch.application.integrations.service import IntegrationService
from fetch.domain.entities import ApiOperation, IntegrationRun, ValidationIssue
from fetch.domain.enums import GenerationLanguage, HttpMethod, SupportStatus
from fetch.domain.errors import IntegrationContextError

_SOURCE_ID = uuid4()
_REVISION_ID = uuid4()
_WORKSPACE_ID = uuid4()
_OP_ID = uuid4()


def _make_operation() -> ApiOperation:
    return ApiOperation(
        id=_OP_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        method=HttpMethod.POST,
        path="/v1/orders",
        path_normalized="/v1/orders",
        operation_id=None,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key="src:1.0:POST:/v1/orders",
        source_pointer=None,
        security_requirements=[],
    )


def _make_context() -> IntegrationContext:
    return IntegrationContext(
        operation=_make_operation(),
        base_url="https://api.example.com",
        auth_schemes=[],
        parameters=[],
        request_body=None,
        request_schema_json=None,
        response_schemas=[],
        examples=[],
        error_definitions=[],
        api_title="Test API",
    )


def _make_service(
    loader: object | None = None,
    llm: object | None = None,
    contract_validator: object | None = None,
    syntax_validator: object | None = None,
    repo: object | None = None,
) -> IntegrationService:
    if loader is None:
        loader = AsyncMock()
        loader.load = AsyncMock(return_value=_make_context())

    if llm is None:
        llm = AsyncMock()
        llm.generate = AsyncMock(return_value="POST /v1/orders\n# generated code")

    if contract_validator is None:
        cv = MagicMock()
        cv.validate = MagicMock(return_value=[])
        contract_validator = cv

    if syntax_validator is None:
        sv = MagicMock()
        sv.validate = MagicMock(return_value=[])
        syntax_validator = sv

    if repo is None:
        repo = AsyncMock()
        repo.save = AsyncMock()

    return IntegrationService(
        context_loader=loader,
        llm_provider=llm,
        contract_validator=contract_validator,
        syntax_validator=syntax_validator,
        integration_repo=repo,
        llm_model_id="test-model",
        llm_max_tokens=1024,
        generation_temperature=0.1,
    )


@pytest.mark.asyncio
async def test_generate_returns_integration_run() -> None:
    service = _make_service()
    run = await service.generate(
        operation_id=_OP_ID,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        language=GenerationLanguage.PYTHON,
    )
    assert isinstance(run, IntegrationRun)
    assert run.language == GenerationLanguage.PYTHON
    assert run.source_id == _SOURCE_ID
    assert run.operation_id == _OP_ID
    assert run.support_status == SupportStatus.SUPPORTED
    assert run.generated_code == "POST /v1/orders\n# generated code"
    assert run.validation_report is not None


@pytest.mark.asyncio
async def test_generate_calls_llm_exactly_once() -> None:
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="POST /v1/orders\n# code")
    service = _make_service(llm=llm)
    await service.generate(
        operation_id=_OP_ID,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        language=GenerationLanguage.PYTHON,
    )
    llm.generate.assert_called_once()


@pytest.mark.asyncio
async def test_generate_persists_run() -> None:
    repo = AsyncMock()
    repo.save = AsyncMock()
    service = _make_service(repo=repo)
    run = await service.generate(
        operation_id=_OP_ID,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        language=GenerationLanguage.PYTHON,
    )
    repo.save.assert_called_once_with(run)


@pytest.mark.asyncio
async def test_generate_validation_failure_in_report() -> None:
    cv = MagicMock()
    cv.validate = MagicMock(
        return_value=[
            ValidationIssue(
                severity="error",
                category="contract",
                message="Method not found",
                field="method",
            )
        ]
    )
    service = _make_service(contract_validator=cv)
    run = await service.generate(
        operation_id=_OP_ID,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        language=GenerationLanguage.PYTHON,
    )
    assert run.validation_report is not None
    assert run.validation_report.overall_valid is False
    assert len(run.validation_report.issues) >= 1
    # run is still returned
    assert isinstance(run, IntegrationRun)


@pytest.mark.asyncio
async def test_generate_context_error_propagates() -> None:
    loader = AsyncMock()
    loader.load = AsyncMock(
        side_effect=IntegrationContextError(
            "Operation not found", operation_id=str(_OP_ID)
        )
    )
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="code")
    service = _make_service(loader=loader, llm=llm)

    with pytest.raises(IntegrationContextError):
        await service.generate(
            operation_id=_OP_ID,
            source_id=_SOURCE_ID,
            revision_id=_REVISION_ID,
            workspace_id=_WORKSPACE_ID,
            language=GenerationLanguage.PYTHON,
        )

    llm.generate.assert_not_called()
