"""Unit tests for fetch_get_auth tool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import ApiSource, AuthScheme, SourceRevision
from fetch.domain.enums import AuthSchemeType, RevisionStatus, SourceType


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


def _make_auth_scheme(revision_id: object) -> AuthScheme:
    from uuid import UUID

    return AuthScheme(
        id=uuid4(),
        revision_id=UUID(str(revision_id)),
        workspace_id=uuid4(),
        name="ApiKey",
        scheme_type=AuthSchemeType.API_KEY,
        description="API Key authentication",
        details_json='{"in": "header", "name": "X-API-Key"}',
    )


@pytest.mark.asyncio
async def test_fetch_get_auth_returns_auth_schemes() -> None:
    source = _make_source()
    revision = _make_revision(source.id)
    scheme = _make_auth_scheme(revision.id)

    mock_source_repo = MagicMock()
    mock_source_repo.get = AsyncMock(return_value=source)

    mock_rev_repo = MagicMock()
    mock_rev_repo.get_active = AsyncMock(return_value=revision)

    mock_auth_repo = MagicMock()
    mock_auth_repo.list_by_revision = AsyncMock(return_value=[scheme])

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.auth.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.auth.PgSourceRepository",
            return_value=mock_source_repo,
        ),
        patch(
            "fetch.mcp.tools.auth.PgRevisionRepository",
            return_value=mock_rev_repo,
        ),
        patch(
            "fetch.mcp.tools.auth.PgAuthSchemeRepository",
            return_value=mock_auth_repo,
        ),
    ):
        from fetch.mcp.tools.auth import fetch_get_auth

        result = await fetch_get_auth(source_id=str(source.id))

    assert isinstance(result, dict)
    assert "auth_schemes" in result
    assert isinstance(result["auth_schemes"], list)
    assert len(result["auth_schemes"]) == 1
    item = result["auth_schemes"][0]
    assert "auth_scheme_id" in item
    assert isinstance(item["auth_scheme_id"], str)
    assert item["name"] == "ApiKey"
    assert "scheme_type" in item
    assert "details_json" in item
