"""Retrieval benchmark runner.

Usage:
    python evals/runners/retrieval_benchmark.py \
        --dataset evals/datasets/petstore.json \
        --source-id <uuid>

Measures Recall@5, Recall@10, and MRR against a dataset of grounded questions.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))

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
from fetch.domain.enums import QueryWorkflow
from fetch.infrastructure.db.repositories import (
    PgChunkRelationRepository,
    PgChunkRepository,
    PgOperationRepository,
    PgQueryRunRepository,
    PgRevisionRepository,
    PgSchemaRepository,
)
from fetch.infrastructure.db.session import get_session, init_db
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider
from fetch.infrastructure.qdrant.repository import QdrantRepository


def _build_retrieval_config(mode: str, settings: Any) -> RetrievalConfig:
    dense_config = DenseRetrievalConfig(
        model_id=settings.embeddings.model_id,
        top_k=settings.retrieval.dense_candidate_limit,
    )
    bm25_config = BM25RetrievalConfig(top_k=settings.retrieval.sparse_candidate_limit)
    fusion_config = FusionConfig(top_k=settings.retrieval.fused_candidate_limit)
    rerank_config = RerankConfig(
        model_id=settings.reranker.model_id,
        top_n=settings.retrieval.rerank_limit,
    )
    expansion_config = ExpansionConfig()

    if mode == "dense":
        bm25_config = BM25RetrievalConfig(top_k=0)
        rerank_config = RerankConfig(model_id=settings.reranker.model_id, top_n=0)
    elif mode == "hybrid":
        rerank_config = RerankConfig(model_id=settings.reranker.model_id, top_n=0)

    return RetrievalConfig(
        dense=dense_config,
        bm25=bm25_config,
        fusion=fusion_config,
        rerank=rerank_config,
        expansion=expansion_config,
    )


async def run_eval(
    dataset: list[dict[str, Any]],
    source_id: UUID,
    revision_id: UUID,
    workspace_id: UUID,
    retrieval_config: RetrievalConfig,
    top_k: int,
    settings: Any,
) -> dict[str, Any]:
    nim = NvidiaNimProvider(
        api_key=settings.llm.api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout_seconds=settings.llm.timeout_seconds,
    )
    qdrant = QdrantRepository()

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

        for item in dataset:
            if item.get("should_abstain"):
                continue

            question = item["question"]
            expected_op = (item.get("expected_operation") or "").lower()
            expected_entity_type = (item.get("expected_entity_type") or "").lower()

            packed, _run = await retrieval_service.retrieve(
                question=question,
                source_id=source_id,
                revision_id=revision_id,
                workspace_id=workspace_id,
                workflow=QueryWorkflow.DOC_QA,
                config=retrieval_config,
            )

            rank: int | None = None
            for i, citation in enumerate(packed.citations, start=1):
                method = (citation.method or "").upper()
                path = citation.path or ""
                op_str = f"{method} {path}".lower()
                entity_type = (citation.entity_type or "").lower()

                match_op = expected_op and op_str == expected_op
                match_entity = expected_entity_type and entity_type == expected_entity_type
                if match_op or match_entity:
                    rank = i
                    break

            rr = 1.0 / rank if rank is not None and rank <= top_k else 0.0
            results.append(
                {
                    "id": item["id"],
                    "question": question,
                    "expected_operation": item.get("expected_operation"),
                    "rank": rank,
                    "reciprocal_rank": rr,
                    "hit_at_5": rank is not None and rank <= 5,
                    "hit_at_10": rank is not None and rank <= 10,
                }
            )

    non_abstain = results
    total = len(non_abstain)
    if total == 0:
        return {"results": results, "metrics": {"recall_at_5": 0.0, "recall_at_10": 0.0, "mrr": 0.0}}

    recall_at_5 = sum(1 for r in non_abstain if r["hit_at_5"]) / total
    recall_at_10 = sum(1 for r in non_abstain if r["hit_at_10"]) / total
    mrr = sum(r["reciprocal_rank"] for r in non_abstain) / total

    return {
        "results": results,
        "metrics": {
            "recall_at_5": round(recall_at_5, 4),
            "recall_at_10": round(recall_at_10, 4),
            "mrr": round(mrr, 4),
            "total_questions": total,
        },
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval benchmark")
    parser.add_argument("--dataset", required=True, help="Path to dataset JSON")
    parser.add_argument("--source-id", required=True, help="UUID of the ingested source")
    parser.add_argument("--top-k", type=int, default=10, help="Top-k threshold")
    parser.add_argument(
        "--mode",
        choices=["full", "hybrid", "dense"],
        default="full",
        help="Retrieval mode",
    )
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    dataset = json.loads(dataset_path.read_text())

    source_id = UUID(args.source_id)
    settings = get_settings()
    init_db()

    # Resolve workspace_id and revision_id
    async with get_session() as session:
        from fetch.infrastructure.db.repositories import PgSourceRepository, PgRevisionRepository

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

    retrieval_config = _build_retrieval_config(args.mode, settings)

    output = await run_eval(
        dataset=dataset,
        source_id=source_id,
        revision_id=revision_id,
        workspace_id=workspace_id,
        retrieval_config=retrieval_config,
        top_k=args.top_k,
        settings=settings,
    )

    metrics = output["metrics"]
    print(f"\nMode: {args.mode}")
    print(f"{'Metric':<20} {'Value':>10}")
    print("-" * 32)
    print(f"{'Recall@5':<20} {metrics['recall_at_5']:>10.4f}")
    print(f"{'Recall@10':<20} {metrics['recall_at_10']:>10.4f}")
    print(f"{'MRR':<20} {metrics['mrr']:>10.4f}")
    print(f"{'Total questions':<20} {metrics['total_questions']:>10}")

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"evals/results/retrieval_{args.mode}_{timestamp}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, indent=2))
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
