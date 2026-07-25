"""Unit tests for DenseRetriever.

Both EmbeddingProvider and QdrantRepository are mocked — no external services.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from fetch.application.retrieval.dense_retriever import (
    DenseRetrievalConfig,
    DenseRetriever,
)
from fetch.domain.protocols import EmbeddingResult
from fetch.infrastructure.qdrant.models import ChunkHit

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def revision_id() -> UUID:
    return uuid4()


@pytest.fixture
def workspace_id() -> UUID:
    return uuid4()


@pytest.fixture
def sample_vector() -> list[float]:
    return [0.1, 0.2, 0.3, 0.4]


@pytest.fixture
def default_config() -> DenseRetrievalConfig:
    return DenseRetrievalConfig(
        model_id="nvidia/nv-embedqa-e5-v5",
        top_k=25,
        embedding_profile_version="v1",
    )


def _make_chunk_hit(score: float = 0.9) -> ChunkHit:
    return ChunkHit(
        chunk_id=uuid4(),
        score=score,
        payload={"chunk_type": "operation", "text": "some text"},
    )


def _make_mocks(
    vector: list[float],
    hits: list[ChunkHit],
) -> tuple[AsyncMock, MagicMock]:
    """Return (embedding_provider_mock, qdrant_mock)."""
    embedding_provider = AsyncMock()
    embedding_provider.embed = AsyncMock(
        return_value=[EmbeddingResult(index=0, vector=vector)]
    )

    qdrant = AsyncMock()
    qdrant.search_dense = AsyncMock(return_value=hits)

    return embedding_provider, qdrant


# ── embed() call contract ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_embed_called_with_query_text(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
    default_config: DenseRetrievalConfig,
) -> None:
    """embed() must be called with the raw query text and input_type='query'."""
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "How does pagination work?",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    embedding_provider.embed.assert_awaited_once_with(
        ["How does pagination work?"],
        model_id=default_config.model_id,
        input_type="query",
    )


@pytest.mark.asyncio
async def test_embed_uses_model_id_from_config(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
) -> None:
    config = DenseRetrievalConfig(model_id="custom/model-v2", top_k=10)
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "some query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=config,
    )

    call_kwargs = embedding_provider.embed.call_args
    assert call_kwargs.kwargs["model_id"] == "custom/model-v2"


# ── search_dense() call contract ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_search_dense_called_with_embedded_vector(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
    default_config: DenseRetrievalConfig,
) -> None:
    """search_dense() must receive the vector produced by embed()."""
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "query text",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    qdrant.search_dense.assert_awaited_once_with(
        query_vector=sample_vector,
        revision_id=revision_id,
        workspace_id=workspace_id,
        embedding_profile_version=default_config.embedding_profile_version,
        top_k=default_config.top_k,
        source_ids=None,
    )


@pytest.mark.asyncio
async def test_top_k_passed_through_from_config(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
) -> None:
    config = DenseRetrievalConfig(model_id="nvidia/nv-embedqa-e5-v5", top_k=5)
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=config,
    )

    call_kwargs = qdrant.search_dense.call_args.kwargs
    assert call_kwargs["top_k"] == 5


@pytest.mark.asyncio
async def test_source_ids_forwarded_when_provided(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
    default_config: DenseRetrievalConfig,
) -> None:
    source_ids = [uuid4(), uuid4()]
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
        source_ids=source_ids,
    )

    call_kwargs = qdrant.search_dense.call_args.kwargs
    assert call_kwargs["source_ids"] == source_ids


@pytest.mark.asyncio
async def test_source_ids_none_when_not_provided(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
    default_config: DenseRetrievalConfig,
) -> None:
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    call_kwargs = qdrant.search_dense.call_args.kwargs
    assert call_kwargs["source_ids"] is None


# ── return value contract ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_chunk_hit_list_from_qdrant(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
    default_config: DenseRetrievalConfig,
) -> None:
    hits = [_make_chunk_hit(0.95), _make_chunk_hit(0.80)]
    embedding_provider, qdrant = _make_mocks(sample_vector, hits)
    retriever = DenseRetriever(embedding_provider, qdrant)

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
    sample_vector: list[float],
    default_config: DenseRetrievalConfig,
) -> None:
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    result = await retriever.retrieve(
        "query with no matches",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    assert result == []


# ── failure path: empty embedding result ─────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_empty_list_when_embedding_provider_returns_nothing(
    revision_id: UUID,
    workspace_id: UUID,
    default_config: DenseRetrievalConfig,
) -> None:
    """If the embedding provider returns an empty list, search is skipped."""
    embedding_provider = AsyncMock()
    embedding_provider.embed = AsyncMock(return_value=[])

    qdrant = AsyncMock()
    qdrant.search_dense = AsyncMock()

    retriever = DenseRetriever(embedding_provider, qdrant)

    result = await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=default_config,
    )

    assert result == []
    qdrant.search_dense.assert_not_awaited()


# ── embedding_profile_version forwarded ──────────────────────────────────────


@pytest.mark.asyncio
async def test_embedding_profile_version_passed_to_qdrant(
    revision_id: UUID,
    workspace_id: UUID,
    sample_vector: list[float],
) -> None:
    config = DenseRetrievalConfig(
        model_id="nvidia/nv-embedqa-e5-v5",
        embedding_profile_version="v2",
    )
    embedding_provider, qdrant = _make_mocks(sample_vector, [])
    retriever = DenseRetriever(embedding_provider, qdrant)

    await retriever.retrieve(
        "query",
        revision_id=revision_id,
        workspace_id=workspace_id,
        config=config,
    )

    call_kwargs = qdrant.search_dense.call_args.kwargs
    assert call_kwargs["embedding_profile_version"] == "v2"
