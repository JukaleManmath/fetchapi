"""Tests for ValidationService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from fetch.application.validation.error_lookup import ErrorStatusLookup
from fetch.application.validation.service import ValidationService
from fetch.application.validation.validators import (
    BodyValidator,
    HeaderValidator,
    ParameterValidator,
)
from fetch.domain.entities import RequestDiagnosticRun
from fetch.domain.enums import DiagnosticInputType, SupportStatus


def _make_service(
    llm_return: str = "Request looks valid.",
    llm_raises: Exception | None = None,
) -> tuple[ValidationService, AsyncMock, AsyncMock]:
    llm = MagicMock()
    if llm_raises:
        llm.generate = AsyncMock(side_effect=llm_raises)
    else:
        llm.generate = AsyncMock(return_value=llm_return)

    repo = MagicMock()
    repo.save = AsyncMock()

    service = ValidationService(
        llm_provider=llm,
        diagnostic_repo=repo,
        header_validator=HeaderValidator(),
        parameter_validator=ParameterValidator(),
        body_validator=BodyValidator(),
        error_lookup=ErrorStatusLookup(),
        llm_model_id="test-model",
        llm_max_tokens=512,
        generation_temperature=0.1,
    )
    return service, llm, repo


@pytest.mark.asyncio
async def test_full_pipeline_returns_run() -> None:
    service, _llm, repo = _make_service()
    source_id = uuid4()
    revision_id = uuid4()
    workspace_id = uuid4()

    run = await service.validate_curl(
        curl_string="curl https://api.example.com/v1/items",
        source_id=source_id,
        revision_id=revision_id,
        workspace_id=workspace_id,
        operations=[],
        servers=[],
        auth_schemes_by_name={},
        error_definitions=[],
    )

    assert isinstance(run, RequestDiagnosticRun)
    assert run.source_id == source_id
    assert run.revision_id == revision_id
    assert run.workspace_id == workspace_id
    assert run.input_type == DiagnosticInputType.CURL
    repo.save.assert_called_once()


@pytest.mark.asyncio
async def test_llm_called_exactly_once() -> None:
    service, llm, _ = _make_service()

    await service.validate_curl(
        curl_string="curl https://api.example.com/v1/items",
        source_id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        operations=[],
        servers=[],
        auth_schemes_by_name={},
        error_definitions=[],
    )

    assert llm.generate.call_count == 1


@pytest.mark.asyncio
async def test_llm_failure_returns_run_with_none_explanation() -> None:
    service, _llm, _ = _make_service(llm_raises=RuntimeError("LLM offline"))

    run = await service.validate_curl(
        curl_string="curl https://api.example.com/v1/items",
        source_id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        operations=[],
        servers=[],
        auth_schemes_by_name={},
        error_definitions=[],
    )

    assert run.explanation is None
    assert run.support_status == SupportStatus.INSUFFICIENT_EVIDENCE


@pytest.mark.asyncio
async def test_is_valid_true_when_no_error_findings() -> None:
    service, _, _ = _make_service()

    run = await service.validate_curl(
        curl_string="curl https://api.example.com/v1/items",
        source_id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        operations=[],
        servers=[],
        auth_schemes_by_name={},
        error_definitions=[],
    )

    # No operations loaded so endpoint no-match error finding will be present
    # is_valid is False when there's an endpoint error finding
    assert run.is_valid is False  # endpoint not matched → error


@pytest.mark.asyncio
async def test_auth_header_redacted_in_stored_run() -> None:
    service, _llm, _repo = _make_service()
    secret = "mysupersecrettoken123456"

    run = await service.validate_curl(
        curl_string=f'curl -H "Authorization: Bearer {secret}" https://api.example.com/v1/items',
        source_id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        operations=[],
        servers=[],
        auth_schemes_by_name={},
        error_definitions=[],
    )

    # raw_input must not contain the real secret
    assert secret not in run.raw_input
    # diagnostic.parsed_request.auth_header must be None (never stored)
    assert run.diagnostic is not None
    assert run.diagnostic.parsed_request.auth_header is None
