from uuid import UUID

from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgRevisionRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_get_auth(source_id: str) -> dict[str, object]:
    """
    Get authentication schemes for an API source: type, scopes, header names.
    source_id: UUID of the source from fetch_list_sources.
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

        auth_repo = PgAuthSchemeRepository(session)
        schemes = await auth_repo.list_by_revision(revision.id)

    return {
        "source_id": source_id,
        "auth_schemes": [
            {
                "auth_scheme_id": str(s.id),
                "name": s.name,
                "scheme_type": s.scheme_type.value,
                "description": s.description,
                "details_json": s.details_json,
            }
            for s in schemes
        ],
    }
