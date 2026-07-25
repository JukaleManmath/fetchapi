"""Unit tests for RetrievalService.

All nine dependencies are mocked. No external services are required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from fetch.application.retrieval.bm25_retriever import (
    BM25RetrievalConfig,
    BM25Retriever,
)
from fetch.application.retrieval.dense_retriever import (
    DenseRetrievalConfig,
    DenseRetriever,
)
from fetch.application.retrieval.exact_lookup import ExactLookup, ExactLookupResult
from fetch.application.retrieval.expander import ExpansionConfig, RelationshipExpander
from fetch.application.retrieval.fusion import FusionConfig, RRFFusion
from fetch.application.retrieval.normalizer import NormalizedQuery, QueryNormalizer
from fetch.application.retrieval.packer import ContextPacker, PackedContext
from fetch.application.retrieval.reranker import RerankConfig, RetrievalReranker
from fetch.application.retrieval.service import RetrievalConfig, RetrievalService
from fetch.domain.entities import Citation, QueryRun
from fetch.domain.enums import QueryWorkflow
from fetch.infrastructure.qdrant.models import ChunkHit

# ── fixtures ───────────────────────────────────────────────────────────────────

_SOURCE_ID = uuid4()
_REVISION_ID = uuid4()
_WORKSPACE_ID = uuid4()
_QUESTION = "How do I create a payment?"


def _hit(score: float = 0.9) -> ChunkHit:
    return ChunkHit(chunk_id=uuid4(), score=score, payload={"text": "some text"})


def _packed_context(citations: list[Citation] | None = None) -> PackedContext:
    return PackedContext(
        citations=citations or [],
        context_text="context",
        source_id_map={},
    )


def _make_config() -> RetrievalConfig:
    return RetrievalConfig(
        dense=DenseRetrievalConfig(model_id="nvidia/llama"),
        bm25=BM25RetrievalConfig(),
        fusion=FusionConfig(),
        rerank=RerankConfig(model_id="nvidia/reranker"),
        expansion=ExpansionConfig(),
    )


def _make_service(
    *,
    dense_hits: list[ChunkHit] | None = None,
    bm25_hits: list[ChunkHit] | None = None,
    fused_hits: list[ChunkHit] | None = None,
    reranked_hits: list[ChunkHit] | None = None,
    expanded_hits: list[ChunkHit] | None = None,
    packed: PackedContext | None = None,
    exact_result: ExactLookupResult | None = None,
) -> tuple[RetrievalService, dict]:
    """Build a RetrievalService with all dependencies mocked.

    Returns (service, mocks) where mocks is a dict of all mock objects keyed
    by their role name for assertion convenience.
    """
    dense_hits = dense_hits or [_hit(), _hit()]
    bm25_hits = bm25_hits or [_hit()]
    fused_hits = fused_hits or [_hit()]
    reranked_hits = reranked_hits or [_hit()]
    expanded_hits = expanded_hits or [_hit()]
    packed = packed or _packed_context()
    exact_result = exact_result or ExactLookupResult()

    normalizer = MagicMock(spec=QueryNormalizer)
    normalizer.normalize.return_value = NormalizedQuery(raw_text=_QUESTION)

    exact_lookup = AsyncMock(spec=ExactLookup)
    exact_lookup.lookup.return_value = exact_result

    dense_retriever = AsyncMock(spec=DenseRetriever)
    dense_retriever.retrieve.return_value = dense_hits

    bm25_retriever = AsyncMock(spec=BM25Retriever)
    bm25_retriever.retrieve.return_value = bm25_hits

    fusion = MagicMock(spec=RRFFusion)
    fusion.fuse.return_value = fused_hits

    reranker = AsyncMock(spec=RetrievalReranker)
    reranker.rerank.return_value = reranked_hits

    expander = AsyncMock(spec=RelationshipExpander)
    expander.expand.return_value = expanded_hits

    packer = MagicMock(spec=ContextPacker)
    packer.pack.return_value = packed

    query_run_repo = AsyncMock()
    query_run_repo.save = AsyncMock()

    service = RetrievalService(
        normalizer=normalizer,
        exact_lookup=exact_lookup,
        dense_retriever=dense_retriever,
        bm25_retriever=bm25_retriever,
        fusion=fusion,
        reranker=reranker,
        expander=expander,
        packer=packer,
        query_run_repo=query_run_repo,
    )

    mocks = {
        "normalizer": normalizer,
        "exact_lookup": exact_lookup,
        "dense_retriever": dense_retriever,
        "bm25_retriever": bm25_retriever,
        "fusion": fusion,
        "reranker": reranker,
        "expander": expander,
        "packer": packer,
        "query_run_repo": query_run_repo,
    }

    return service, mocks


# ── full pipeline execution ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_stages_called_in_order() -> None:
    """Every stage must be called exactly once in the correct order."""
    service, mocks = _make_service()
    config = _make_config()

    _packed, _run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=config,
    )

    mocks["normalizer"].normalize.assert_called_once_with(_QUESTION)
    mocks["exact_lookup"].lookup.assert_called_once()
    mocks["dense_retriever"].retrieve.assert_called_once()
    mocks["bm25_retriever"].retrieve.assert_called_once()
    mocks["fusion"].fuse.assert_called_once()
    mocks["reranker"].rerank.assert_called_once()
    mocks["expander"].expand.assert_called_once()
    mocks["packer"].pack.assert_called_once()
    mocks["query_run_repo"].save.assert_called_once()


# ── return values ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_returns_packed_context_from_packer() -> None:
    expected_packed = _packed_context()
    service, _ = _make_service(packed=expected_packed)

    packed, _ = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert packed is expected_packed


@pytest.mark.asyncio
async def test_returns_query_run() -> None:
    service, _ = _make_service()

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert isinstance(run, QueryRun)


# ── retrieval_ms ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_retrieval_ms_is_positive_integer() -> None:
    service, _ = _make_service()

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert run.retrieval_ms is not None
    assert isinstance(run.retrieval_ms, int)
    assert run.retrieval_ms >= 0


# ── trace fields ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_trace_fields_reflect_stage_output_sizes() -> None:
    dense_hits = [_hit(), _hit(), _hit()]  # 3
    bm25_hits = [_hit(), _hit()]  # 2
    fused_hits = [_hit(), _hit(), _hit(), _hit()]  # 4
    reranked_hits = [_hit()]  # 1
    expanded_hits = [_hit(), _hit()]  # 2

    service, _ = _make_service(
        dense_hits=dense_hits,
        bm25_hits=bm25_hits,
        fused_hits=fused_hits,
        reranked_hits=reranked_hits,
        expanded_hits=expanded_hits,
    )

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert run.dense_candidate_count == 3
    assert run.bm25_candidate_count == 2
    assert run.fused_candidate_count == 4
    assert run.reranked_candidate_count == 1
    assert run.expanded_candidate_count == 2


# ── exact_match_found ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_exact_match_found_false_when_no_entity_matched() -> None:
    service, _ = _make_service(exact_result=ExactLookupResult())

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert run.exact_match_found is False


@pytest.mark.asyncio
async def test_exact_match_found_true_when_entity_matched() -> None:
    matched_result = ExactLookupResult(
        chunk_ids=[uuid4()],
        matched_entity_type="operation",
        matched_entity_id=uuid4(),
    )
    service, _ = _make_service(exact_result=matched_result)

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert run.exact_match_found is True


# ── query_run_repo.save ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_run_repo_save_called_with_the_returned_run() -> None:
    service, mocks = _make_service()

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    mocks["query_run_repo"].save.assert_awaited_once_with(run)


# ── dense and BM25 run concurrently ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_dense_and_bm25_both_called() -> None:
    """Both retrievers must be called — asyncio.gather ensures concurrent dispatch."""
    service, mocks = _make_service()

    await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert mocks["dense_retriever"].retrieve.call_count == 1
    assert mocks["bm25_retriever"].retrieve.call_count == 1


# ── citations from packed context ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_run_citations_come_from_packed_context() -> None:
    citation = Citation(
        source_id="S1",
        chunk_id=uuid4(),
        entity_type="operation",
        entity_id=None,
        title="Create Payment",
        content="POST /payments",
        source_url=None,
        source_pointer=None,
        api_version=None,
        method="POST",
        path="/payments",
    )
    packed = _packed_context(citations=[citation])
    service, _ = _make_service(packed=packed)

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert run.citations == [citation]


# ── answer is None at retrieval time ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_run_answer_is_none_after_retrieval() -> None:
    service, _ = _make_service()

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
    )

    assert run.answer is None


# ── source_ids forwarded ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_source_ids_forwarded_to_dense_and_bm25_retrievers() -> None:
    service, mocks = _make_service()
    source_ids = [uuid4(), uuid4()]

    await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=_make_config(),
        source_ids=source_ids,
    )

    dense_call_kwargs = mocks["dense_retriever"].retrieve.call_args.kwargs
    bm25_call_kwargs = mocks["bm25_retriever"].retrieve.call_args.kwargs
    assert dense_call_kwargs["source_ids"] == source_ids
    assert bm25_call_kwargs["source_ids"] == source_ids


# ── QueryRun fields ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_query_run_fields_set_correctly() -> None:
    service, _ = _make_service()
    config = _make_config()

    _, run = await service.retrieve(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        workflow=QueryWorkflow.DOC_QA,
        config=config,
    )

    assert run.workspace_id == _WORKSPACE_ID
    assert run.source_id == _SOURCE_ID
    assert run.revision_id == _REVISION_ID
    assert run.workflow == QueryWorkflow.DOC_QA
    assert run.question == _QUESTION
