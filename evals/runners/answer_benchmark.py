"""Answer benchmark runner.

Usage:
    python evals/runners/answer_benchmark.py \
        --dataset evals/datasets/petstore.json \
        --source-id <uuid>

Measures citation accuracy, abstention accuracy, and groundedness.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))

from fetch.application.queries.events import DoneEvent, ResultEvent
from fetch.application.queries.service import QueryService
from fetch.application.retrieval.bm25_retriever import BM25RetrievalConfig, BM25Retriever
from fetch.application.retrieval.dense_retriever import DenseRetrievalConfig, DenseRetriever
from fetch.application.retrieval.exact_lookup import ExactLookup
from fetch.application.retrieval.expander import ExpansionConfig, RelationshipExpander
from fetch.application.retrieval.fusion import FusionConfig, RRFFusion
from fetch.application.retrieval.normalizer import QueryNormalizer
from fetch.application.retrieval.packer import ContextPacker
from fetch.application.retrieval.reranker import RerankConfig, RetrievalReranker
from fetch.application.retrieval.service import RetrievalConfig, RetrievalService
from fetch.config import get_settings
from fetch.domain.enums import QueryWorkflow, SupportStatus
from fetch.infrastructure.db.repositories import (
    PgChunkRelationRepository,
    PgChunkRepository,
    PgOperationRepository,
    PgQueryRunRepository,
    PgRevisionRepository,
    PgSchemaRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session, init_db
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.qdrant.repository import QdrantRepository


async def _stream_to_result(
    svc: QueryService,
    question: str,
    source_id: UUID,
    revision_id: UUID,
    workspace_id: UUID,
) -> dict[str, Any]:
    full_text = ""
    citations: list[Any] = []
    support_status: SupportStatus = SupportStatus.INSUFFICIENT_EVIDENCE

    async for event in svc.stream(
        question=question,
        source_id=source_id,
        revision_id=revision_id,
        workspace_id=workspace_id,
    ):
        from fetch.application.queries.events import TokenEvent, EvidenceEvent

        if isinstance(event, TokenEvent):
            full_text += event.text
        elif isinstance(event, EvidenceEvent):
            citations = event.citations
        elif isinstance(event, ResultEvent):
            support_status = event.support_status

    return {
        "answer": full_text,
        "citations": citations,
        "support_status": support_status,
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Answer benchmark")
    parser.add_argument("--dataset", required=True, help="Path to dataset JSON")
    parser.add_argument("--source-id", required=True, help="UUID of the ingested source")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    dataset: list[dict[str, Any]] = json.loads(dataset_path.read_text())

    source_id = UUID(args.source_id)
    settings = get_settings()
    init_db()

    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)

        source = await source_repo.get(source_id)
        if source is None:
            print(f"ERROR: source {source_id} not found", file=sys.stderr)
            sys.exit(1)

        revision = await rev_repo.get_active(source_id)
        if revision is None:
            print(f"ERROR: no active revision for source {source_id}", file=sys.stderr)
            sys.exit(1)

        workspace_id = source.workspace_id
        revision_id = revision.id

        from sqlalchemy import text as sa_text
        row = await session.execute(
            sa_text("SELECT id FROM embedding_profiles WHERE dense_model_id = :model ORDER BY created_at LIMIT 1"),
            {"model": settings.embeddings.model_id},
        )
        profile_row = row.fetchone()
        embedding_profile_version = str(profile_row[0]) if profile_row else "v1"

    nim = NvidiaNimProvider(
        api_key=settings.llm.api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout_seconds=settings.llm.timeout_seconds,
    )
    qdrant = QdrantRepository()

    retrieval_config = RetrievalConfig(
        dense=DenseRetrievalConfig(
            model_id=settings.embeddings.model_id,
            top_k=settings.retrieval.dense_candidate_limit,
            embedding_profile_version=embedding_profile_version,
        ),
        bm25=BM25RetrievalConfig(top_k=settings.retrieval.sparse_candidate_limit, embedding_profile_version=embedding_profile_version),
        fusion=FusionConfig(top_k=settings.retrieval.fused_candidate_limit),
        rerank=RerankConfig(
            model_id=settings.reranker.model_id,
            top_n=settings.retrieval.rerank_limit,
        ),
        expansion=ExpansionConfig(),
    )

    results: list[dict[str, Any]] = []

    async with get_session() as session:
        chunk_repo = PgChunkRepository(session)
        chunk_relation_repo = PgChunkRelationRepository(session)
        operation_repo = PgOperationRepository(session)
        schema_repo = PgSchemaRepository(session)
        query_run_repo = PgQueryRunRepository(session)

        normalizer = QueryNormalizer()
        exact_lookup = ExactLookup(
            operation_repo=operation_repo,
            schema_repo=schema_repo,
            chunk_repo=chunk_repo,
        )
        dense_retriever = DenseRetriever(embedding_provider=nim, qdrant=qdrant)
        bm25_retriever = BM25Retriever(qdrant=qdrant)
        fusion = RRFFusion()
        reranker = RetrievalReranker(rerank_provider=nim)
        expander = RelationshipExpander(
            relation_repo=chunk_relation_repo,
            chunk_repo=chunk_repo,
        )
        packer = ContextPacker()

        retrieval_service = RetrievalService(
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

        svc = QueryService(
            retrieval_service=retrieval_service,
            llm_provider=nim,  # type: ignore[arg-type]
            query_run_repo=query_run_repo,
            retrieval_config=retrieval_config,
            llm_model_id=settings.llm.model_id,
            llm_max_tokens=settings.llm.max_tokens,
            abstention_min_chunks=settings.llm.abstention_min_chunks,
            generation_temperature=settings.llm.generation_temperature,
        )

        for item in dataset:
            question = item["question"]
            should_abstain = item.get("should_abstain", False)
            expected_op = (item.get("expected_operation") or "").lower()
            expected_contains = [t.lower() for t in item.get("expected_citation_contains", [])]

            result = await _stream_to_result(
                svc=svc,
                question=question,
                source_id=source_id,
                revision_id=revision_id,
                workspace_id=workspace_id,
            )

            answer_text = result["answer"].lower()
            citations = result["citations"]
            support_status: SupportStatus = result["support_status"]
            abstained = support_status == SupportStatus.INSUFFICIENT_EVIDENCE

            # Citation accuracy (non-abstention only)
            citation_hit: bool | None = None
            if not should_abstain:
                for citation in citations:
                    method = (getattr(citation, "method", None) or "").upper()
                    path = getattr(citation, "path", None) or ""
                    op_str = f"{method} {path}".lower().strip()
                    if expected_op and op_str == expected_op:
                        citation_hit = True
                        break
                if citation_hit is None:
                    citation_hit = False

            # Abstention accuracy
            abstention_correct: bool
            if should_abstain:
                abstention_correct = abstained
            else:
                abstention_correct = not abstained

            # Groundedness (non-abstention only)
            grounded: bool | None = None
            if not should_abstain and expected_contains:
                grounded = all(term in answer_text for term in expected_contains)

            results.append(
                {
                    "id": item["id"],
                    "question": question,
                    "should_abstain": should_abstain,
                    "abstained": abstained,
                    "abstention_correct": abstention_correct,
                    "citation_hit": citation_hit,
                    "grounded": grounded,
                    "support_status": support_status.value,
                }
            )

    non_abstain = [r for r in results if not r["should_abstain"]]
    all_questions = results

    citation_accuracy = (
        sum(1 for r in non_abstain if r["citation_hit"]) / len(non_abstain)
        if non_abstain
        else 0.0
    )
    abstention_accuracy = (
        sum(1 for r in all_questions if r["abstention_correct"]) / len(all_questions)
        if all_questions
        else 0.0
    )
    grounded_questions = [r for r in non_abstain if r["grounded"] is not None]
    groundedness = (
        sum(1 for r in grounded_questions if r["grounded"]) / len(grounded_questions)
        if grounded_questions
        else 0.0
    )

    metrics = {
        "citation_accuracy": round(citation_accuracy, 4),
        "abstention_accuracy": round(abstention_accuracy, 4),
        "groundedness": round(groundedness, 4),
        "total_questions": len(all_questions),
        "non_abstention_questions": len(non_abstain),
    }

    print(f"\n{'Metric':<30} {'Value':>10}")
    print("-" * 42)
    print(f"{'Citation accuracy':<30} {metrics['citation_accuracy']:>10.4f}")
    print(f"{'Abstention accuracy':<30} {metrics['abstention_accuracy']:>10.4f}")
    print(f"{'Groundedness':<30} {metrics['groundedness']:>10.4f}")
    print(f"{'Total questions':<30} {metrics['total_questions']:>10}")

    output = {"results": results, "metrics": metrics}

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"evals/results/answer_{timestamp}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
