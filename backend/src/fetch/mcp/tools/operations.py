from uuid import UUID

from fetch.infrastructure.db.repositories import PgOperationRepository
from fetch.infrastructure.db.session import get_session
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_get_operation(operation_id: str) -> dict[str, object]:
    """
    Get full operation detail: method, path, parameters, request body, responses, auth.
    operation_id: UUID of the operation from fetch_search_docs results.
    """
    op_uuid = UUID(operation_id)
    async with get_session() as session:
        repo = PgOperationRepository(session)
        op = await repo.get(op_uuid)

    if op is None:
        return {"error": "OPERATION_NOT_FOUND", "message": "Operation not found."}

    return {
        "operation_id": str(op.id),
        "method": op.method.value,
        "path": op.path,
        "path_normalized": op.path_normalized,
        "summary": op.summary,
        "description": op.description,
        "tags": op.tags,
        "deprecated": op.deprecated,
        "operation_id_str": op.operation_id,
        "security_requirements": op.security_requirements,
        "source_pointer": op.source_pointer,
    }
