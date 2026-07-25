from uuid import UUID

from fetch.config import get_settings
from fetch.domain.enums import GenerationLanguage
from fetch.domain.errors import IntegrationContextError
from fetch.infrastructure.db.repositories import (
    PgOperationRepository,
    PgRevisionRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.mcp.dependencies import get_integration_service
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_generate_integration(
    operation_id: str,
    language: str = "python",
) -> dict[str, object]:
    """
    Generate working integration code for an API operation.
    operation_id: UUID of the operation.
    language: "python", "typescript", or "java".
    Returns generated code, contract validation results, and syntax validation results.
    """
    settings = get_settings()
    workspace_id = settings.app.workspace_id
    op_uuid = UUID(operation_id)

    try:
        lang = GenerationLanguage(language.lower())
    except ValueError:
        return {
            "error": "INVALID_LANGUAGE",
            "message": f"Unsupported language '{language}'. Use python, typescript, or java.",
        }

    async with get_session() as session:
        operation_repo = PgOperationRepository(session)
        op = await operation_repo.get(op_uuid)
        if op is None:
            return {"error": "OPERATION_NOT_FOUND", "message": "Operation not found."}

        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get_active(op.revision_id)
        if revision is None:
            return {
                "error": "NO_ACTIVE_REVISION",
                "message": "No active revision found for this operation.",
            }

        source_repo = PgSourceRepository(session)
        source = await source_repo.get(revision.source_id)
        if source is None:
            return {"error": "SOURCE_NOT_FOUND", "message": "Source not found."}

        svc = get_integration_service(session)

        try:
            run = await svc.generate(
                operation_id=op_uuid,
                source_id=source.id,
                revision_id=revision.id,
                workspace_id=workspace_id,
                language=lang,
            )
        except IntegrationContextError as exc:
            return {"error": "OPERATION_NOT_FOUND", "message": str(exc)}

    report = run.validation_report
    report_dict: dict[str, object] = {
        "contract_valid": False,
        "syntax_valid": False,
        "overall_valid": False,
        "issues": [],
    }
    if report is not None:
        report_dict = {
            "contract_valid": report.contract_valid,
            "syntax_valid": report.syntax_valid,
            "overall_valid": report.overall_valid,
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "field": i.field,
                }
                for i in report.issues
            ],
        }

    return {
        "integration_run_id": str(run.id),
        "operation_id": str(run.operation_id),
        "language": run.language.value,
        "generated_code": run.generated_code,
        "validation_report": report_dict,
        "support_status": run.support_status.value,
        "warnings": run.warnings,
    }
