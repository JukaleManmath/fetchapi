from uuid import UUID

from fetch.domain.errors import IncompatibleSourceError, RevisionNotFoundError
from fetch.infrastructure.db.session import get_session
from fetch.mcp.dependencies import get_version_diff_service
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_compare_versions(
    source_id: str,
    version_a: str,
    version_b: str,
) -> dict[str, object]:
    """
    Compare two revisions of the same API source.
    Returns added/removed/changed operations, schemas, and auth schemes.
    source_id: UUID of the source.
    version_a: Version label of the first revision (e.g. "1.0.0").
    version_b: Version label of the second revision (e.g. "1.1.0").
    """
    src_uuid = UUID(source_id)

    async with get_session() as session:
        svc = get_version_diff_service(session)

        try:
            diff = await svc.diff(
                source_id=src_uuid,
                version_a=version_a,
                version_b=version_b,
            )
        except RevisionNotFoundError as exc:
            return {"error": "REVISION_NOT_FOUND", "message": str(exc)}
        except IncompatibleSourceError as exc:
            return {"error": "INCOMPATIBLE_SOURCE", "message": str(exc)}

    return {
        "source_id": str(diff.source_id),
        "revision_a_id": str(diff.revision_a_id),
        "revision_b_id": str(diff.revision_b_id),
        "revision_a_version": diff.revision_a_version,
        "revision_b_version": diff.revision_b_version,
        "summary": diff.summary,
        "operations_added": [
            {
                "operation_id": str(op.operation_id),
                "method": op.method,
                "path": op.path,
                "change_type": op.change_type,
                "changed_fields": op.changed_fields,
            }
            for op in diff.operations_added
        ],
        "operations_removed": [
            {
                "operation_id": str(op.operation_id),
                "method": op.method,
                "path": op.path,
                "change_type": op.change_type,
                "changed_fields": op.changed_fields,
            }
            for op in diff.operations_removed
        ],
        "operations_changed": [
            {
                "operation_id": str(op.operation_id),
                "method": op.method,
                "path": op.path,
                "change_type": op.change_type,
                "changed_fields": op.changed_fields,
            }
            for op in diff.operations_changed
        ],
        "schemas_added": [
            {
                "schema_id": str(s.schema_id),
                "name": s.name,
                "change_type": s.change_type,
                "changed_fields": s.changed_fields,
            }
            for s in diff.schemas_added
        ],
        "schemas_removed": [
            {
                "schema_id": str(s.schema_id),
                "name": s.name,
                "change_type": s.change_type,
                "changed_fields": s.changed_fields,
            }
            for s in diff.schemas_removed
        ],
        "schemas_changed": [
            {
                "schema_id": str(s.schema_id),
                "name": s.name,
                "change_type": s.change_type,
                "changed_fields": s.changed_fields,
            }
            for s in diff.schemas_changed
        ],
        "auth_added": [
            {"name": a.name, "change_type": a.change_type} for a in diff.auth_added
        ],
        "auth_removed": [
            {"name": a.name, "change_type": a.change_type} for a in diff.auth_removed
        ],
    }
