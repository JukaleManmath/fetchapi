from uuid import UUID

from fetch.config import get_settings
from fetch.domain.errors import CurlParseError
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgErrorRepository,
    PgOperationRepository,
    PgResponseRepository,
    PgRevisionRepository,
    PgServerRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.mcp.dependencies import get_validation_service
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_validate_request(
    source_id: str,
    curl_command: str,
) -> dict[str, object]:
    """
    Validate a curl command against the API spec.
    Returns findings (missing headers, wrong content-type, schema violations)
    and a corrected example.
    source_id: UUID of the source.
    curl_command: The raw curl command string to validate.
    """
    settings = get_settings()
    workspace_id = settings.app.workspace_id
    src_uuid = UUID(source_id)

    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        source = await source_repo.get(src_uuid)
        if source is None or source.workspace_id != workspace_id:
            return {"error": "SOURCE_NOT_FOUND", "message": "Source not found."}

        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get_active(src_uuid)
        if revision is None:
            return {
                "error": "NO_ACTIVE_REVISION",
                "message": "No active revision found.",
            }

        revision_id = revision.id
        operation_repo = PgOperationRepository(session)
        server_repo = PgServerRepository(session)
        auth_scheme_repo = PgAuthSchemeRepository(session)

        operations = await operation_repo.list_by_revision(revision_id)
        servers = await server_repo.list_by_revision(revision_id)
        auth_schemes = await auth_scheme_repo.list_by_revision(revision_id)
        auth_schemes_by_name = {s.name: s for s in auth_schemes}

        svc = get_validation_service(session)

        try:
            run = await svc.validate_curl(
                curl_string=curl_command,
                source_id=src_uuid,
                revision_id=revision_id,
                workspace_id=workspace_id,
                operations=operations,
                servers=servers,
                auth_schemes_by_name=auth_schemes_by_name,
                error_definitions=[],
                received_status_code=None,
            )
        except CurlParseError as exc:
            return {"error": "CURL_PARSE_ERROR", "message": str(exc)}

    findings: list[dict[str, object]] = []
    if run.diagnostic:
        findings = [
            {
                "severity": f.severity,
                "category": str(f.category),
                "message": f.message,
                "field": f.field,
                "canonical_value": f.canonical_value,
            }
            for f in run.diagnostic.findings
        ]

    return {
        "diagnostic_run_id": str(run.id),
        "is_valid": run.is_valid,
        "support_status": run.support_status.value,
        "findings": findings,
        "corrected_curl": run.corrected_curl,
    }


@mcp.tool()
async def fetch_explain_error(
    source_id: str,
    operation_id: str,
    status_code: int,
) -> dict[str, object]:
    """
    Explain a status code in the context of a specific API operation.
    Returns spec-defined response schema, common causes, and suggested fixes.
    source_id: UUID of the source.
    operation_id: UUID of the operation.
    status_code: The HTTP status code received (e.g. 422, 401, 404).
    """
    settings = get_settings()
    workspace_id = settings.app.workspace_id
    src_uuid = UUID(source_id)
    op_uuid = UUID(operation_id)
    status_str = str(status_code)

    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        source = await source_repo.get(src_uuid)
        if source is None or source.workspace_id != workspace_id:
            return {"error": "SOURCE_NOT_FOUND", "message": "Source not found."}

        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get_active(src_uuid)
        if revision is None:
            return {
                "error": "NO_ACTIVE_REVISION",
                "message": "No active revision found.",
            }

        revision_id = revision.id

        response_repo = PgResponseRepository(session)
        error_repo = PgErrorRepository(session)

        responses = await response_repo.list_by_operation(op_uuid)
        error_defs = await error_repo.find_by_status_code(revision_id, status_str)

    matched_response = next((r for r in responses if r.status_code == status_str), None)

    return {
        "source_id": source_id,
        "operation_id": operation_id,
        "status_code": status_code,
        "documented_response": {
            "status_code": matched_response.status_code,
            "description": matched_response.description,
            "content_schemas": matched_response.content_schemas,
        }
        if matched_response
        else None,
        "error_definitions": [
            {
                "id": str(e.id),
                "status_code": e.status_code,
                "error_code": e.error_code,
                "title": e.title,
                "description": e.description,
            }
            for e in error_defs
        ],
        "is_documented": matched_response is not None or len(error_defs) > 0,
    }
