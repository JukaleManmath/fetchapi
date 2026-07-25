"""Unit tests for fetch_list_sources tool."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import ApiSource, SourceRevision
from fetch.domain.enums import RevisionStatus, SourceType


def _make_source() -> ApiSource:
    return ApiSource(
        id=uuid4(),
        workspace_id=uuid4(),
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
        expected_chunk_count=10,
        actual_chunk_count=10,
        created_at=datetime.now(UTC),
        activated_at=datetime.now(UTC),
        failed_at=None,
        failure_reason=None,
    )


@pytest.mark.asyncio
async def test_fetch_list_sources_returns_dict() -> None:
    source = _make_source()
    revision = _make_revision(source.id)

    mock_source_repo = MagicMock()
    mock_source_repo.list_by_workspace = AsyncMock(return_value=[source])

    mock_rev_repo = MagicMock()
    mock_rev_repo.get_active = AsyncMock(return_value=revision)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "fetch.mcp.tools.sources.get_session",
            return_value=mock_session,
        ),
        patch(
            "fetch.mcp.tools.sources.PgSourceRepository",
            return_value=mock_source_repo,
        ),
        patch(
            "fetch.mcp.tools.sources.PgRevisionRepository",
            return_value=mock_rev_repo,
        ),
    ):
        from fetch.mcp.tools.sources import fetch_list_sources

        result = await fetch_list_sources()

    assert isinstance(result, dict)
    assert "sources" in result
    assert isinstance(result["sources"], list)
    assert len(result["sources"]) == 1
    item = result["sources"][0]
    assert "id" in item
    assert isinstance(item["id"], str)
    assert item["name"] == "Test API"
    assert item["active_revision"] == str(revision.id)
    assert item["source_version"] == "1.0.0"
