"""RetrievalService — wires all retrieval stages into a single pipeline call.

Pipeline order:
  normalize → exact lookup → dense + BM25 (concurrent) → RRF fuse →
  rerank → expand → pack → trace → persist QueryRun

The QueryRun returned has retrieval_ms and all trace fields set.
answer is None at this point — generation is the responsibility of a separate
service (CLAUDE.md §6: one generation call per answer).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from uuid import UUID, uuid4

from fetch.application.retrieval.bm25_retriever import (
    BM25RetrievalConfig,
    BM25Retriever,
)
from fetch.application.retrieval.dense_retriever import (
    DenseRetrievalConfig,
    DenseRetriever,
)
from fetch.application.retrieval.exact_lookup import ExactLookup
from fetch.application.retrieval.expander import ExpansionConfig, RelationshipExpander
from fetch.application.retrieval.fusion import FusionConfig, RRFFusion
from fetch.application.retrieval.normalizer import QueryNormalizer
from fetch.application.retrieval.packer import ContextPacker, PackedContext
from fetch.application.retrieval.reranker import RerankConfig, RetrievalReranker
from fetch.domain.entities import QueryRun
from fetch.domain.enums import QueryWorkflow, SupportStatus
from fetch.domain.protocols import QueryRunRepository

logger = logging.getLogger(__name__)

_MAX_LOG_QUESTION_LEN = 200


def _redact_question(question: str) -> str:
    """Truncate questions longer than the log limit to avoid oversized log lines."""
    if len(question) > _MAX_LOG_QUESTION_LEN:
        return question[:_MAX_LOG_QUESTION_LEN] + "…[truncated]"
    return question


@dataclass(frozen=True)
class RetrievalConfig:
    """Aggregated configuration passed to :class:`RetrievalService.retrieve`."""

    dense: DenseRetrievalConfig
    bm25: BM25RetrievalConfig
    fusion: FusionConfig
    rerank: RerankConfig
    expansion: ExpansionConfig
    final_evidence_limit: int = 10  # cap applied after expansion, before packing


class RetrievalService:
    """Orchestrates the full retrieval pipeline for a single query."""

    def __init__(
        self,
        normalizer: QueryNormalizer,
        exact_lookup: ExactLookup,
        dense_retriever: DenseRetriever,
        bm25_retriever: BM25Retriever,
        fusion: RRFFusion,
        reranker: RetrievalReranker,
        expander: RelationshipExpander,
        packer: ContextPacker,
        query_run_repo: QueryRunRepository,
    ) -> None:
        self._normalizer = normalizer
        self._exact_lookup = exact_lookup
        self._dense_retriever = dense_retriever
        self._bm25_retriever = bm25_retriever
        self._fusion = fusion
        self._reranker = reranker
        self._expander = expander
        self._packer = packer
        self._query_run_repo = query_run_repo

    async def retrieve(
        self,
        question: str,
        source_id: UUID,
        revision_id: UUID,
        workspace_id: UUID,
        workflow: QueryWorkflow,
        config: RetrievalConfig,
        source_ids: list[UUID] | None = None,
    ) -> tuple[PackedContext, QueryRun]:
        """Run the full retrieval pipeline and return (PackedContext, QueryRun).

        The QueryRun has retrieval_ms and all trace fields populated and is
        persisted before returning.  answer is None — generation happens later.

        Args:
            question: The raw user question.
            source_id: The ApiSource being queried.
            revision_id: The active SourceRevision to search within.
            workspace_id: Tenant isolation boundary.
            workflow: The named retrieval workflow (used for QueryRun.workflow).
            config: Per-stage tuning parameters.
            source_ids: Optional additional source UUID filter forwarded to
                dense and BM25 retrievers for cross-source queries.
        """
        t0 = time.monotonic()

        # 1. Normalise
        normalized = self._normalizer.normalize(question)

        # 2. Exact PG lookup
        exact_result = await self._exact_lookup.lookup(
            normalized, revision_id, workspace_id
        )

        # 3. Dense + BM25 concurrently
        dense_hits, bm25_hits = await asyncio.gather(
            self._dense_retriever.retrieve(
                query_text=question,
                revision_id=revision_id,
                workspace_id=workspace_id,
                config=config.dense,
                source_ids=source_ids,
            ),
            self._bm25_retriever.retrieve(
                query_text=question,
                revision_id=revision_id,
                workspace_id=workspace_id,
                config=config.bm25,
                source_ids=source_ids,
            ),
        )

        # 4. RRF fusion
        fused = self._fusion.fuse([dense_hits, bm25_hits], config.fusion)

        # 5. Rerank
        reranked = await self._reranker.rerank(question, fused, config.rerank)

        # 6. Relationship expansion
        expanded = await self._expander.expand(reranked, revision_id, config.expansion)

        # 7. Cap evidence then pack context
        capped = expanded[:config.final_evidence_limit] if config.final_evidence_limit > 0 else expanded
        packed = self._packer.pack(capped)

        retrieval_ms = int((time.monotonic() - t0) * 1000)

        # 8. Build QueryRun with all trace fields
        run = QueryRun(
            id=uuid4(),
            workspace_id=workspace_id,
            source_id=source_id,
            revision_id=revision_id,
            workflow=workflow,
            question=question,
            answer=None,
            citations=packed.citations,
            support_status=SupportStatus.INSUFFICIENT_EVIDENCE,
            retrieval_ms=retrieval_ms,
            dense_candidate_count=len(dense_hits),
            bm25_candidate_count=len(bm25_hits),
            fused_candidate_count=len(fused),
            reranked_candidate_count=len(reranked),
            expanded_candidate_count=len(expanded),
            exact_match_found=exact_result.matched_entity_id is not None,
        )

        # 9. Persist
        await self._query_run_repo.save(run)

        logger.info(
            "retrieval_complete",
            extra={
                "run_id": str(run.id),
                "question": _redact_question(question),
                "dense_candidates": run.dense_candidate_count,
                "bm25_candidates": run.bm25_candidate_count,
                "fused_candidates": run.fused_candidate_count,
                "reranked_candidates": run.reranked_candidate_count,
                "expanded_candidates": run.expanded_candidate_count,
                "exact_match_found": run.exact_match_found,
                "retrieval_ms": retrieval_ms,
            },
        )

        return packed, run
