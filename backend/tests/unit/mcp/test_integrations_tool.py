"""Unit tests for fetch_generate_integration tool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import ApiOperation, IntegrationRun, ValidationReport
from fetch.domain.enums import (
    GenerationLanguage,
    HttpMethod,
    RevisionStatus,
    SupportStatus,
)


def _make_operation(revision_id: object) -> ApiOperation:
    from uuid import UUID

    return ApiOperation(
        id=uuid4(),
        revision_id=UUID(str(revision_id)),
        workspace_id=uuid4(),
        method=HttpMethod.POST,
        path="/v1/items",
        path_normalized="/v1/items",
        operation_id="createItem",
        summary="Create item",
        description=None,
        tags=[],
        deprecated=False,
        logical_key="src:1.0:POST:/v1/items",
        source_pointer=None,
    )


def _make_revision(source_id: object) -> object:
    from uuid import UUID

    from fetch.domain.entities import SourceRevision

    return SourceRevision(
        id=uuid4(),
        source_id=UUID(str(source_id)),
        workspace_id=uuid4(),
        status=RevisionStatus.ACTIVE,
        content_hash="abc",
        snapshot_object_key=None,
        api_version="1.0.0",
        api_title="Test API",
        expected_chunk_count=5,
        actual_chunk_count=5,
        created_at=datetime.now(UTC),
        activated_at=datetime.now(UTC),
        failed_at=None,
        failure_reason=None,
    )


def _make_source(workspace_id: object) -> object:
    from uuid import UUID

    from fetch.domain.entities import ApiSource
    from fetch.domain.enums import SourceType

    return ApiSource(
        id=uuid4(),
        workspace_id=UUID(str(workspace_id)),
        name="Test API",
        source_type=SourceType.OPENAPI_URL,
        config_url="https://example.com/openapi.yaml",
        config_object_key=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_integration_run(
    operation_id: object, source_id: object, revision_id: object
) -> IntegrationRun:
    from uuid import UUID

    report = ValidationReport(
        contract_valid=True,
        syntax_valid=True,
        overall_valid=True,
        issues=[],
    )
    return IntegrationRun(
        id=uuid4(),
        workspace_id=uuid4(),
        source_id=UUID(str(source_id)),
        revision_id=UUID(str(revision_id)),
        operation_id=UUID(str(operation_id)),
        language=GenerationLanguage.PYTHON,
        generated_code="import httpx\nresponse = httpx.post('/v1/items')",
        validation_report=report,
        support_status=SupportStatus.SUPPORTED,
        warnings=[],
        prompt_version="v1",
        prompt_tokens=100,
        completion_tokens=200,
        context_assembly_ms=50,
        generation_ms=300,
        validation_ms=20,
        total_ms=370,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_fetch_generate_integration_returns_code() -> None:
    source_id = uuid4()
    revision = _make_revision(source_id)
    source = _make_source(uuid4())
    op = _make_operation(revision.id)
    run = _make_integration_run(op.id, source.id, revision.id)

    mock_op_repo = MagicMock()
    mock_op_repo.get = AsyncMock(return_value=op)

    mock_rev_repo = MagicMock()
    mock_rev_repo.get_active = AsyncMock(return_value=revision)

    mock_source_repo = MagicMock()
    mock_source_repo.get = AsyncMock(return_value=source)

    mock_svc = MagicMock()
    mock_svc.generate = AsyncMock(return_value=run)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.integrations.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.integrations.PgOperationRepository",
            return_value=mock_op_repo,
        ),
        patch(
            "fetch.mcp.tools.integrations.PgRevisionRepository",
            return_value=mock_rev_repo,
        ),
        patch(
            "fetch.mcp.tools.integrations.PgSourceRepository",
            return_value=mock_source_repo,
        ),
        patch(
            "fetch.mcp.tools.integrations.get_integration_service",
            return_value=mock_svc,
        ),
    ):
        from fetch.mcp.tools.integrations import fetch_generate_integration

        result = await fetch_generate_integration(
            operation_id=str(op.id),
            language="python",
        )

    assert isinstance(result, dict)
    assert "integration_run_id" in result
    assert isinstance(result["integration_run_id"], str)
    assert "generated_code" in result
    assert "validation_report" in result
    assert "support_status" in result
    assert isinstance(result["validation_report"], dict)
    assert "contract_valid" in result["validation_report"]
