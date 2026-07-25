"""Unit tests for QueryService.

All external dependencies are mocked. No database or LLM required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from fetch.application.queries.events import (
    DoneEvent,
    ErrorEvent,
    ResultEvent,
    StartEvent,
    TokenEvent,
)
from fetch.application.queries.service import QueryService
from fetch.application.retrieval.bm25_retriever import BM25RetrievalConfig
from fetch.application.retrieval.dense_retriever import DenseRetrievalConfig
from fetch.application.retrieval.expander import ExpansionConfig
from fetch.application.retrieval.fusion import FusionConfig
from fetch.application.retrieval.packer import PackedContext
from fetch.application.retrieval.reranker import RerankConfig
from fetch.application.retrieval.service import RetrievalConfig, RetrievalService
from fetch.domain.entities import Citation, QueryRun
from fetch.domain.enums import QueryWorkflow, SupportStatus
from fetch.domain.protocols import StreamChunk

# ── Fixtures ───────────────────────────────────────────────────────────────────

_SOURCE_ID = uuid4()
_REVISION_ID = uuid4()
_WORKSPACE_ID = uuid4()
_RUN_ID = uuid4()
_QUESTION = "How do I create a payment?"

_RETRIEVAL_CONFIG = RetrievalConfig(
    dense=DenseRetrievalConfig(model_id="test-model"),
    bm25=BM25RetrievalConfig(),
    fusion=FusionConfig(),
    rerank=RerankConfig(model_id="test-reranker"),
    expansion=ExpansionConfig(),
)


def _make_citation(source_id: str = "S1") -> Citation:
    return Citation(
        source_id=source_id,
        chunk_id=uuid4(),
        entity_type="operation",
        entity_id=uuid4(),
        title="Create Payment",
        content="POST /v1/payments creates a payment.",
        source_url=None,
        source_pointer=None,
        api_version=None,
        method="POST",
        path="/v1/payments",
    )


def _make_query_run(run_id: UUID | None = None) -> QueryRun:
    return QueryRun(
        id=run_id or _RUN_ID,
        workspace_id=_WORKSPACE_ID,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workflow=QueryWorkflow.DOC_QA,
        question=_QUESTION,
        answer=None,
        retrieval_ms=50,
    )


def _make_packed_context(
    citations: list[Citation] | None = None,
    source_id_map: dict[str, UUID] | None = None,
) -> PackedContext:
    if citations is None:
        citations = [_make_citation("S1")]
    if source_id_map is None:
        source_id_map = {c.source_id: c.chunk_id for c in citations}
    return PackedContext(
        citations=citations,
        context_text="[S1] operation — Create Payment\nPOST /v1/payments creates a payment.",
        source_id_map=source_id_map,
    )


def _make_service(
    retrieval_service: RetrievalService | None = None,
    llm_provider: object | None = None,
    query_run_repo: object | None = None,
) -> QueryService:
    return QueryService(
        retrieval_service=retrieval_service or MagicMock(spec=RetrievalService),
        llm_provider=llm_provider or MagicMock(),
        query_run_repo=query_run_repo or AsyncMock(),
        retrieval_config=_RETRIEVAL_CONFIG,
        llm_model_id="test-model",
        llm_max_tokens=4096,
        abstention_min_chunks=1,
        generation_temperature=0.1,
    )


async def _collect_events(service: QueryService) -> list[object]:
    events = []
    async for event in service.stream(
        question=_QUESTION,
        source_id=_SOURCE_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
    ):
        events.append(event)
    return events


# ── Test 1: Abstention ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_abstention_when_no_citations() -> None:
    """With empty citations, skip LLM and emit StartEvent + ResultEvent(INSUFFICIENT_EVIDENCE) + DoneEvent."""
    run = _make_query_run()
    empty_packed = PackedContext(citations=[], context_text="", source_id_map={})

    retrieval_mock = MagicMock(spec=RetrievalService)
    retrieval_mock.retrieve = AsyncMock(return_value=(empty_packed, run))

    llm_mock = MagicMock()
    llm_mock.generate_stream = AsyncMock()

    query_run_repo = AsyncMock()

    svc = _make_service(
        retrieval_service=retrieval_mock,
        llm_provider=llm_mock,
        query_run_repo=query_run_repo,
    )

    events = await _collect_events(svc)

    assert len(events) == 3
    assert isinstance(events[0], StartEvent)
    assert isinstance(events[1], ResultEvent)
    assert events[1].support_status == SupportStatus.INSUFFICIENT_EVIDENCE
    assert events[1].cited_source_ids == []
    assert isinstance(events[2], DoneEvent)
    # LLM must never be called
    llm_mock.generate_stream.assert_not_called()
    # Run must be saved
    query_run_repo.save.assert_called_once()


# ── Test 2: Successful generation ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_successful_generation_events_in_order() -> None:
    """Happy path: events must be Start → Evidence → Token(s) → Result → Done."""
    run = _make_query_run()
    packed = _make_packed_context()

    retrieval_mock = MagicMock(spec=RetrievalService)
    retrieval_mock.retrieve = AsyncMock(return_value=(packed, run))

    async def _fake_stream(*args, **kwargs):
        yield StreamChunk(text="The payment endpoint is [S1].")
        yield StreamChunk(text=" Use POST.", usage=None)

    llm_mock = MagicMock()
    llm_mock.generate_stream = AsyncMock(return_value=_fake_stream())

    query_run_repo = AsyncMock()

    svc = _make_service(
        retrieval_service=retrieval_mock,
        llm_provider=llm_mock,
        query_run_repo=query_run_repo,
    )

    events = await _collect_events(svc)

    event_types = [type(e).__name__ for e in events]
    assert event_types[0] == "StartEvent"
    assert event_types[1] == "EvidenceEvent"
    # Tokens come next
    token_events = [e for e in events if isinstance(e, TokenEvent)]
    assert len(token_events) == 2
    # Result and Done at end
    assert isinstance(events[-2], ResultEvent)
    assert isinstance(events[-1], DoneEvent)
    # S1 is a valid citation
    result_event: ResultEvent = events[-2]  # type: ignore[assignment]
    assert "S1" in result_event.cited_source_ids


# ── Test 3: Unknown ID rejection ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_id_rejected_and_warning_added() -> None:
    """[S99] is not in allowed IDs: must appear in warnings, not cited_source_ids, status PARTIALLY_SUPPORTED."""
    run = _make_query_run()
    packed = _make_packed_context()

    retrieval_mock = MagicMock(spec=RetrievalService)
    retrieval_mock.retrieve = AsyncMock(return_value=(packed, run))

    async def _fake_stream(*args, **kwargs):
        yield StreamChunk(text="See [S1] and [S99] for more info.")

    llm_mock = MagicMock()
    llm_mock.generate_stream = AsyncMock(return_value=_fake_stream())

    query_run_repo = AsyncMock()

    svc = _make_service(
        retrieval_service=retrieval_mock,
        llm_provider=llm_mock,
        query_run_repo=query_run_repo,
    )

    events = await _collect_events(svc)

    result_event = next(e for e in events if isinstance(e, ResultEvent))
    assert "S99" not in result_event.cited_source_ids
    assert "S1" in result_event.cited_source_ids
    assert result_event.support_status == SupportStatus.PARTIALLY_SUPPORTED
    assert any("S99" in w for w in result_event.warnings)


# ── Test 4: Provider exception ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_exception_emits_error_event() -> None:
    """When LLM raises an exception, ErrorEvent is emitted and run saved with INSUFFICIENT_EVIDENCE."""
    run = _make_query_run()
    packed = _make_packed_context()

    retrieval_mock = MagicMock(spec=RetrievalService)
    retrieval_mock.retrieve = AsyncMock(return_value=(packed, run))

    async def _failing_stream(*args, **kwargs):
        raise RuntimeError("connection refused")
        yield  # make it an async generator  # noqa: unreachable

    llm_mock = MagicMock()
    llm_mock.generate_stream = AsyncMock(side_effect=RuntimeError("connection refused"))

    query_run_repo = AsyncMock()

    svc = _make_service(
        retrieval_service=retrieval_mock,
        llm_provider=llm_mock,
        query_run_repo=query_run_repo,
    )

    events = await _collect_events(svc)

    error_events = [e for e in events if isinstance(e, ErrorEvent)]
    assert len(error_events) == 1
    assert error_events[0].code == "PROVIDER_ERROR"
    assert error_events[0].retryable is True

    # Run must be saved with INSUFFICIENT_EVIDENCE
    query_run_repo.save.assert_called()
    saved_run: QueryRun = query_run_repo.save.call_args[0][0]
    assert saved_run.support_status == SupportStatus.INSUFFICIENT_EVIDENCE
