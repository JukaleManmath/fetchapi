from uuid import UUID

from fetch.infrastructure.db.repositories import PgSchemaRepository
from fetch.infrastructure.db.session import get_session
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_get_schema(schema_id: str) -> dict[str, object]:
    """
    Get full schema definition with all properties, types, and constraints.
    schema_id: UUID of the schema from fetch_search_docs results.
    """
    schema_uuid = UUID(schema_id)
    async with get_session() as session:
        repo = PgSchemaRepository(session)
        schema = await repo.get(schema_uuid)

    if schema is None:
        return {"error": "SCHEMA_NOT_FOUND", "message": "Schema not found."}

    return {
        "schema_id": str(schema.id),
        "name": schema.name,
        "description": schema.description,
        "schema_json": schema.schema_json,
        "nullable": schema.nullable,
        "deprecated": schema.deprecated,
        "source_pointer": schema.source_pointer,
    }
