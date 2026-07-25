"""Unit tests for fetch_search_docs tool."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.application.queries.events import ResultEvent, TokenEvent
from fetch.domain.enums import RevisionStatus, SupportStatus


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


async def _fake_stream(*args: object, **kwargs: object) -> AsyncIterator[object]:
    query_id = uuid4()
    yield TokenEvent(text="Hello ")
    yield TokenEvent(text="world.")
    yield ResultEvent(
        query_id=query_id,
        cited_source_ids=["S1"],
        support_status=SupportStatus.SUPPORTED,
        warnings=[],
        usage=None,
        latency_ms={"retrieval_ms": 10, "generation_ms": 20, "total_ms": 30},
    )


@pytest.mark.asyncio
async def test_fetch_search_docs_returns_dict() -> None:
    source_id = str(uuid4())
    revision = _make_revision(source_id)

    mock_rev_repo = MagicMock()
    mock_rev_repo.get_active = AsyncMock(return_value=revision)

    mock_svc = MagicMock()
    mock_svc.stream = _fake_stream

    mock_bundle = MagicMock()
    mock_bundle.service = mock_svc
    mock_bundle.llm_provider = AsyncMock()
    mock_bundle.llm_provider.aclose = AsyncMock()

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.search.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.search.PgRevisionRepository",
            return_value=mock_rev_repo,
        ),
        patch(
            "fetch.mcp.tools.search.get_query_service",
            return_value=mock_bundle,
        ),
    ):
        from fetch.mcp.tools.search import fetch_search_docs

        result = await fetch_search_docs(
            source_id=source_id,
            query="how do I authenticate?",
        )

    assert isinstance(result, dict)
    assert "answer" in result
    assert "citations" in result
    assert "support_status" in result
    assert "active_revision" in result
    assert result["answer"] == "Hello world."
    assert result["support_status"] == SupportStatus.SUPPORTED.value
