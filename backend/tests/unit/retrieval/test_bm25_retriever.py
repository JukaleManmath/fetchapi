"""Unit tests for BM25Retriever.

QdrantRepository is mocked — no external services required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from fetch.application.retrieval.bm25_retriever import (
    BM25RetrievalConfig,
    BM25Retriever,
)
from fetch.infrastructure.qdrant.models import ChunkHit

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def revision_id() -> UUID:
    return uuid4()


@pytest.fixture
def workspace_id() -> UUID:
    return uuid4()


@pytest.fixture
def default_config() -> BM25RetrievalConfig:
    return BM25RetrievalConfig(top_k=25, embedding_profile_version="v1")


def _make_chunk_hit(score: float = 1.0) -> ChunkHit:
    return ChunkHit(
        chunk_id=uuid4(),
        score=score,
        payload={"chunk_type": "operation", "text": "some text"},
    )


def _make_qdrant_mock(hits: list[ChunkHit]) -> AsyncMock:
    qdrant = AsyncMock()
    qdrant.search_bm25 = AsyncMock(return_value=hits)
    return qdrant


# ── search_bm25() call contract ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_bm25_called_with_correct_args(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: BM25RetrievalConfig,
) -> None:
    """search_bm25 must receive all mandatory tenant arguments from the config."""
    qdrant = _make_qdrant_mock([])
    retriever = BM25Retriever(qdrant)

    await retriever.retrieve(
        "list all endpoints",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    qdrant.search_bm25.assert_awaited_once_with(
        query_text="list all endpoints",
        revision_id=revision_id,
        workspace_id=workspace_id,
        embedding_profile_version=default_config.embedding_profile_version,
        top_k=default_config.top_k,
        source_ids=None,
    )


@pytest.mark.asyncio
async def test_source_ids_forwarded_when_provided(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: BM25RetrievalConfig,
) -> None:
    source_ids = [uuid4(), uuid4()]
    qdrant = _make_qdrant_mock([])
    retriever = BM25Retriever(qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
        source_ids=source_ids,
    )

    call_kwargs = qdrant.search_bm25.call_args.kwargs
    assert call_kwargs["source_ids"] == source_ids


@pytest.mark.asyncio
async def test_source_ids_none_when_not_provided(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: BM25RetrievalConfig,
) -> None:
    qdrant = _make_qdrant_mock([])
    retriever = BM25Retriever(qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    call_kwargs = qdrant.search_bm25.call_args.kwargs
    assert call_kwargs["source_ids"] is None


@pytest.mark.asyncio
async def test_top_k_passed_from_config(
    revision_id: UUID,
    workspace_id: UUID,
) -> None:
    config = BM25RetrievalConfig(top_k=10)
    qdrant = _make_qdrant_mock([])
    retriever = BM25Retriever(qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=config,
    )

    call_kwargs = qdrant.search_bm25.call_args.kwargs
    assert call_kwargs["top_k"] == 10


@pytest.mark.asyncio
async def test_embedding_profile_version_passed_from_config(
    revision_id: UUID,
    workspace_id: UUID,
) -> None:
    config = BM25RetrievalConfig(embedding_profile_version="v2")
    qdrant = _make_qdrant_mock([])
    retriever = BM25Retriever(qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=config,
    )

    call_kwargs = qdrant.search_bm25.call_args.kwargs
    assert call_kwargs["embedding_profile_version"] == "v2"


# ── return value contract ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_chunk_hits_from_qdrant(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: BM25RetrievalConfig,
) -> None:
    hits = [_make_chunk_hit(), _make_chunk_hit()]
    qdrant = _make_qdrant_mock(hits)
    retriever = BM25Retriever(qdrant)

    result = await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    assert result == hits


@pytest.mark.asyncio
async def test_returns_empty_list_when_no_hits(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: BM25RetrievalConfig,
) -> None:
    qdrant = _make_qdrant_mock([])
    retriever = BM25Retriever(qdrant)

    result = await retriever.retrieve(
        "obscure query with no matches",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    assert result == []


# ── score passthrough ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_scores_passed_through_unchanged(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: BM25RetrievalConfig,
) -> None:
    """BM25Retriever must not mutate the scores returned by the repository."""
    hits = [_make_chunk_hit(score=1.0), _make_chunk_hit(score=1.0)]
    qdrant = _make_qdrant_mock(hits)
    retriever = BM25Retriever(qdrant)

    result = await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    assert all(hit.score == 1.0 for hit in result)
