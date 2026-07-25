"""Ablation runner — compares dense, hybrid, and hybrid+rerank retrieval modes.

Usage:
    python evals/runners/ablation.py \
        --dataset evals/datasets/petstore.json \
        --source-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))

from fetch.config import get_settings
from fetch.infrastructure.db.repositories import PgRevisionRepository, PgSourceRepository
from fetch.infrastructure.db.session import get_session, init_db

# Import the core eval function from retrieval_benchmark
sys.path.insert(0, str(Path(__file__).resolve().parent))
from retrieval_benchmark import _build_retrieval_config, run_eval  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval ablation study")
    parser.add_argument("--dataset", required=True, help="Path to dataset JSON")
    parser.add_argument("--source-id", required=True, help="UUID of the ingested source")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    dataset = json.loads(dataset_path.read_text())

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

    modes = [
        ("dense", "dense"),
        ("hybrid", "hybrid"),
        ("hybrid+rerank", "full"),
    ]

    all_results: dict[str, object] = {}

    print(f"\n{'Mode':<16} {'Recall@5':>10} {'Recall@10':>11} {'MRR':>8}")
    print("-" * 48)

    for label, mode in modes:
        retrieval_config = _build_retrieval_config(mode, settings, embedding_profile_version)
        output = await run_eval(
            dataset=dataset,
            source_id=source_id,
            revision_id=revision_id,
            workspace_id=workspace_id,
            retrieval_config=retrieval_config,
            top_k=10,
            settings=settings,
        )
        metrics = output["metrics"]
        all_results[label] = output

        print(
            f"{label:<16} {metrics['recall_at_5']:>10.4f} "
            f"{metrics['recall_at_10']:>11.4f} {metrics['mrr']:>8.4f}"
        )

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"evals/results/ablation_{timestamp}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(all_results, indent=2, default=str))
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
