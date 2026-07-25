"""Unit tests for RetrievalReranker.

Pure Python — no external services required. RerankProvider is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from fetch.application.retrieval.reranker import RerankConfig, RetrievalReranker
from fetch.domain.protocols import RerankCandidate, RerankResult
from fetch.infrastructure.qdrant.models import ChunkHit

# ── helpers ────────────────────────────────────────────────────────────────────


def _hit(
    text: str = "some text",
    score: float = 1.0,
    extra_payload: dict | None = None,
) -> ChunkHit:
    payload: dict = {"text": text}
    if extra_payload:
        payload.update(extra_payload)
    return ChunkHit(chunk_id=uuid4(), score=score, payload=payload)


def _make_provider(return_value: list[RerankResult]) -> AsyncMock:
    provider = AsyncMock()
    provider.rerank = AsyncMock(return_value=return_value)
    return provider


# ── empty input ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_candidates_returns_empty_without_calling_provider() -> None:
    provider = _make_provider([])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="rerank-model", top_n=10)

    result = await reranker.rerank(query="q", candidates=[], config=config)

    assert result == []
    provider.rerank.assert_not_called()


# ── provider call arguments ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_called_with_correct_query_and_model_id() -> None:
    hits = [_hit("doc A"), _hit("doc B")]
    provider = _make_provider([RerankResult(index=0, score=0.9)])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="my-rerank-model", top_n=5)

    await reranker.rerank(query="find something", candidates=hits, config=config)

    provider.rerank.assert_called_once()
    call_kwargs = provider.rerank.call_args
    assert call_kwargs.kwargs["query"] == "find something"
    assert call_kwargs.kwargs["model_id"] == "my-rerank-model"
    assert call_kwargs.kwargs["top_n"] == 5


@pytest.mark.asyncio
async def test_provider_called_with_correct_candidates() -> None:
    hits = [_hit("first doc"), _hit("second doc")]
    provider = _make_provider([RerankResult(index=0, score=0.9)])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=10)

    await reranker.rerank(query="q", candidates=hits, config=config)

    passed_candidates: list[RerankCandidate] = provider.rerank.call_args.kwargs[
        "candidates"
    ]
    assert len(passed_candidates) == 2
    assert passed_candidates[0].index == 0
    assert passed_candidates[0].text == "first doc"
    assert passed_candidates[1].index == 1
    assert passed_candidates[1].text == "second doc"


@pytest.mark.asyncio
async def test_missing_text_in_payload_uses_empty_string() -> None:
    """A hit with no 'text' key in payload must produce an empty-string candidate."""
    hit = ChunkHit(chunk_id=uuid4(), score=1.0, payload={"other": "data"})
    provider = _make_provider([RerankResult(index=0, score=0.5)])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=10)

    await reranker.rerank(query="q", candidates=[hit], config=config)

    passed_candidates: list[RerankCandidate] = provider.rerank.call_args.kwargs[
        "candidates"
    ]
    assert passed_candidates[0].text == ""


# ── score replacement ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_output_score_is_reranker_score_not_original() -> None:
    hit = _hit(score=0.123)
    reranker_score = 0.987
    provider = _make_provider([RerankResult(index=0, score=reranker_score)])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=10)

    result = await reranker.rerank(query="q", candidates=[hit], config=config)

    assert len(result) == 1
    assert result[0].score == reranker_score


# ── ordering ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_output_order_follows_provider_result_order() -> None:
    """Provider already returns results sorted descending — reranker must preserve that."""
    hits = [_hit("A"), _hit("B"), _hit("C")]
    # Provider scores: B > A > C  (indices 1, 0, 2)
    provider_results = [
        RerankResult(index=1, score=0.9),
        RerankResult(index=0, score=0.7),
        RerankResult(index=2, score=0.3),
    ]
    provider = _make_provider(provider_results)
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=10)

    result = await reranker.rerank(query="q", candidates=hits, config=config)

    assert len(result) == 3
    assert result[0].chunk_id == hits[1].chunk_id
    assert result[1].chunk_id == hits[0].chunk_id
    assert result[2].chunk_id == hits[2].chunk_id
    assert result[0].score == 0.9
    assert result[1].score == 0.7
    assert result[2].score == 0.3


# ── top_n truncation ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_top_n_truncation_delegated_to_provider() -> None:
    """top_n is passed to the provider which applies truncation — reranker returns
    exactly what the provider returns."""
    hits = [_hit() for _ in range(5)]
    # Provider respects top_n=2 and returns only two results.
    provider_results = [
        RerankResult(index=0, score=0.9),
        RerankResult(index=2, score=0.5),
    ]
    provider = _make_provider(provider_results)
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=2)

    result = await reranker.rerank(query="q", candidates=hits, config=config)

    assert len(result) == 2
    assert provider.rerank.call_args.kwargs["top_n"] == 2


# ── payload preservation ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_payload_preserved_on_output_chunks() -> None:
    payload = {"text": "hello", "operation_id": "get_users", "extra": 42}
    hit = ChunkHit(chunk_id=uuid4(), score=0.1, payload=payload)
    provider = _make_provider([RerankResult(index=0, score=0.8)])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=10)

    result = await reranker.rerank(query="q", candidates=[hit], config=config)

    assert result[0].payload == payload


@pytest.mark.asyncio
async def test_chunk_id_preserved_on_output_chunks() -> None:
    chunk_id = uuid4()
    hit = ChunkHit(chunk_id=chunk_id, score=0.5, payload={"text": "x"})
    provider = _make_provider([RerankResult(index=0, score=0.75)])
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=10)

    result = await reranker.rerank(query="q", candidates=[hit], config=config)

    assert result[0].chunk_id == chunk_id


# ── multiple hits with mixed order ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_full_rerank_flow_multiple_hits() -> None:
    """End-to-end: 4 hits come in, provider reorders them, top_n=3 returned."""
    hits = [
        _hit("doc 0", extra_payload={"op": "a"}),
        _hit("doc 1", extra_payload={"op": "b"}),
        _hit("doc 2", extra_payload={"op": "c"}),
        _hit("doc 3", extra_payload={"op": "d"}),
    ]
    provider_results = [
        RerankResult(index=3, score=0.95),
        RerankResult(index=1, score=0.80),
        RerankResult(index=0, score=0.60),
        # index=2 is cut by top_n=3 — provider only returns 3
    ]
    provider = _make_provider(provider_results)
    reranker = RetrievalReranker(provider)
    config = RerankConfig(model_id="model", top_n=3)

    result = await reranker.rerank(query="q", candidates=hits, config=config)

    assert len(result) == 3
    assert result[0].chunk_id == hits[3].chunk_id
    assert result[0].payload["op"] == "d"
    assert result[0].score == 0.95

    assert result[1].chunk_id == hits[1].chunk_id
    assert result[1].score == 0.80

    assert result[2].chunk_id == hits[0].chunk_id
    assert result[2].score == 0.60
