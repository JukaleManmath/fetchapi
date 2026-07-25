"""Validation benchmark runner.

Usage:
    python evals/runners/validation_benchmark.py \
        --source-id <uuid> \
        --fixtures evals/fixtures/validation/broken_requests.json

Measures is_valid accuracy and finding category precision/recall.
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

from fetch.application.validation.error_lookup import ErrorStatusLookup
from fetch.application.validation.service import ValidationService
from fetch.application.validation.validators import (
    BodyValidator,
    HeaderValidator,
    ParameterValidator,
)
from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgDiagnosticRunRepository,
    PgErrorRepository,
    PgOperationRepository,
    PgRevisionRepository,
    PgServerRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session, init_db
from fetch.infrastructure.llm.nvidia_nim import NvidiaNimProvider


async def main() -> None:
    parser = argparse.ArgumentParser(description="Validation benchmark")
    parser.add_argument(
        "--fixtures",
        default="evals/fixtures/validation/broken_requests.json",
        help="Path to fixtures JSON",
    )
    parser.add_argument("--source-id", required=True, help="UUID of the ingested source")
    parser.add_argument("--output", default=None, help="Output JSON path")
    args = parser.parse_args()

    fixtures_path = Path(args.fixtures)
    fixtures: list[dict[str, Any]] = json.loads(fixtures_path.read_text())

    source_id = UUID(args.source_id)
    settings = get_settings()
    init_db()

    nim = NvidiaNimProvider(
        api_key=settings.llm.api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        timeout_seconds=settings.llm.timeout_seconds,
    )

    results: list[dict[str, Any]] = []

    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)
        operation_repo = PgOperationRepository(session)
        server_repo = PgServerRepository(session)
        auth_scheme_repo = PgAuthSchemeRepository(session)
        error_repo = PgErrorRepository(session)
        diagnostic_repo = PgDiagnosticRunRepository(session)

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

        operations = await operation_repo.list_by_revision(revision_id)
        servers = await server_repo.list_by_revision(revision_id)
        auth_schemes = await auth_scheme_repo.list_by_revision(revision_id)
        auth_schemes_by_name = {s.name: s for s in auth_schemes}

        service = ValidationService(
            llm_provider=nim,  # type: ignore[arg-type]
            diagnostic_repo=diagnostic_repo,
            header_validator=HeaderValidator(),
            parameter_validator=ParameterValidator(),
            body_validator=BodyValidator(),
            error_lookup=ErrorStatusLookup(),
            llm_model_id=settings.llm.model_id,
            llm_max_tokens=settings.llm.max_tokens,
            generation_temperature=settings.llm.generation_temperature,
        )

        for fixture in fixtures:
            curl_command = fixture["curl_command"]
            expected_is_valid = fixture["expected_is_valid"]
            expected_findings = fixture.get("expected_findings", [])
            received_status_code = fixture.get("received_status_code")

            error_definitions = []
            if received_status_code:
                error_definitions = await error_repo.find_by_status_code(
                    revision_id, received_status_code
                )

            run = await service.validate_curl(
                curl_string=curl_command,
                source_id=source_id,
                revision_id=revision_id,
                workspace_id=workspace_id,
                operations=operations,
                servers=servers,
                auth_schemes_by_name=auth_schemes_by_name,
                error_definitions=error_definitions,
                received_status_code=received_status_code,
            )

            is_valid_correct = run.is_valid == expected_is_valid

            actual_categories = {
                f.category.value for f in (run.diagnostic.findings if run.diagnostic else [])
            }
            expected_categories = {ef["category"] for ef in expected_findings}

            true_positives = actual_categories & expected_categories
            precision = (
                len(true_positives) / len(actual_categories) if actual_categories else 1.0
            )
            recall = (
                len(true_positives) / len(expected_categories) if expected_categories else 1.0
            )

            results.append(
                {
                    "id": fixture["id"],
                    "is_valid_correct": is_valid_correct,
                    "expected_is_valid": expected_is_valid,
                    "actual_is_valid": run.is_valid,
                    "expected_categories": list(expected_categories),
                    "actual_categories": list(actual_categories),
                    "category_precision": round(precision, 4),
                    "category_recall": round(recall, 4),
                }
            )

    total = len(results)
    is_valid_accuracy = sum(1 for r in results if r["is_valid_correct"]) / total if total else 0.0
    avg_precision = sum(r["category_precision"] for r in results) / total if total else 0.0
    avg_recall = sum(r["category_recall"] for r in results) / total if total else 0.0

    metrics = {
        "is_valid_accuracy": round(is_valid_accuracy, 4),
        "finding_precision": round(avg_precision, 4),
        "finding_recall": round(avg_recall, 4),
        "total_fixtures": total,
    }

    print(f"\n{'Metric':<30} {'Value':>10}")
    print("-" * 42)
    print(f"{'is_valid accuracy':<30} {metrics['is_valid_accuracy']:>10.4f}")
    print(f"{'Finding precision':<30} {metrics['finding_precision']:>10.4f}")
    print(f"{'Finding recall':<30} {metrics['finding_recall']:>10.4f}")
    print(f"{'Total fixtures':<30} {metrics['total_fixtures']:>10}")

    output = {"results": results, "metrics": metrics}

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    output_path = args.output or f"evals/results/validation_{timestamp}.json"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(output, indent=2, default=str))
    print(f"\nResults written to {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
