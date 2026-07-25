"""Unit tests for fetch_validate_request and fetch_explain_error tools."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import (
    ApiSource,
    DiagnosticFinding,
    ParsedRequest,
    RequestDiagnostic,
    RequestDiagnosticRun,
    SourceRevision,
)
from fetch.domain.enums import (
    DiagnosticCategory,
    DiagnosticInputType,
    RevisionStatus,
    SourceType,
    SupportStatus,
)


def _make_source() -> ApiSource:
    from fetch.config import get_settings

    return ApiSource(
        id=uuid4(),
        workspace_id=get_settings().app.workspace_id,
        name="Test API",
        source_type=SourceType.OPENAPI_URL,
        config_url="https://example.com/openapi.yaml",
        config_object_key=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_revision(source_id: object) -> SourceRevision:
    from uuid import UUID

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


def _make_diagnostic_run(
    source_id: object, revision_id: object
) -> RequestDiagnosticRun:
    from uuid import UUID

    parsed = ParsedRequest(
        method="GET",
        url="https://example.com/v1/items",
        headers={},
        body_raw=None,
        body_json=None,
        content_type=None,
        auth_header=None,
        query_params={},
        is_url_encoded_body=False,
    )
    finding = DiagnosticFinding(
        severity="error",
        category=DiagnosticCategory.AUTH,
        message="Missing Authorization header",
        field="authorization",
        canonical_value=None,
    )
    diagnostic = RequestDiagnostic(
        parsed_request=parsed,
        endpoint_match=None,
        findings=[finding],
        error_status_match=None,
        corrected_curl='curl -H "Authorization: Bearer TOKEN" https://example.com/v1/items',
        is_valid=False,
    )
    return RequestDiagnosticRun(
        id=uuid4(),
        workspace_id=uuid4(),
        source_id=UUID(str(source_id)),
        revision_id=UUID(str(revision_id)),
        operation_id=None,
        input_type=DiagnosticInputType.CURL,
        raw_input="curl https://example.com/v1/items",
        parsed_method="GET",
        parsed_url="https://example.com/v1/items",
        received_status_code=None,
        diagnostic=diagnostic,
        explanation=None,
        corrected_curl=diagnostic.corrected_curl,
        is_valid=False,
        support_status=SupportStatus.SUPPORTED,
        prompt_version=None,
        prompt_tokens=None,
        completion_tokens=None,
        parse_ms=5,
        match_ms=10,
        validate_ms=15,
        explanation_ms=None,
        total_ms=30,
        created_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_fetch_validate_request_returns_findings() -> None:
    source = _make_source()
    revision = _make_revision(source.id)
    run = _make_diagnostic_run(source.id, revision.id)

    mock_source_repo = MagicMock()
    mock_source_repo.get = AsyncMock(return_value=source)

    mock_rev_repo = MagicMock()
    mock_rev_repo.get_active = AsyncMock(return_value=revision)

    mock_op_repo = MagicMock()
    mock_op_repo.list_by_revision = AsyncMock(return_value=[])

    mock_server_repo = MagicMock()
    mock_server_repo.list_by_revision = AsyncMock(return_value=[])

    mock_auth_repo = MagicMock()
    mock_auth_repo.list_by_revision = AsyncMock(return_value=[])

    mock_error_repo = MagicMock()
    mock_error_repo.find_by_status_code = AsyncMock(return_value=[])

    mock_svc = MagicMock()
    mock_svc.validate_curl = AsyncMock(return_value=run)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.validation.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.validation.PgSourceRepository",
            return_value=mock_source_repo,
        ),
        patch(
            "fetch.mcp.tools.validation.PgRevisionRepository",
            return_value=mock_rev_repo,
        ),
        patch(
            "fetch.mcp.tools.validation.PgOperationRepository",
            return_value=mock_op_repo,
        ),
        patch(
            "fetch.mcp.tools.validation.PgServerRepository",
            return_value=mock_server_repo,
        ),
        patch(
            "fetch.mcp.tools.validation.PgAuthSchemeRepository",
            return_value=mock_auth_repo,
        ),
        patch(
            "fetch.mcp.tools.validation.PgErrorRepository",
            return_value=mock_error_repo,
        ),
        patch(
            "fetch.mcp.tools.validation.get_validation_service",
            return_value=mock_svc,
        ),
    ):
        from fetch.mcp.tools.validation import fetch_validate_request

        result = await fetch_validate_request(
            source_id=str(source.id),
            curl_command="curl https://example.com/v1/items",
        )

    assert isinstance(result, dict)
    assert "diagnostic_run_id" in result
    assert isinstance(result["diagnostic_run_id"], str)
    assert "is_valid" in result
    assert "findings" in result
    assert isinstance(result["findings"], list)
    assert len(result["findings"]) == 1
    assert "corrected_curl" in result
