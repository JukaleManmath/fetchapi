from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    PgRevisionRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_list_sources() -> dict[str, object]:
    """List all ingested API sources with their active revision status."""
    settings = get_settings()
    workspace_id = settings.app.workspace_id
    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        rev_repo = PgRevisionRepository(session)
        sources = await source_repo.list_by_workspace(workspace_id)

        results = []
        for s in sources:
            active_rev = await rev_repo.get_active(s.id)
            results.append(
                {
                    "id": str(s.id),
                    "name": s.name,
                    "active_revision": str(active_rev.id) if active_rev else None,
                    "source_version": active_rev.api_version
                    if active_rev
                    else "unknown",
                    "status": active_rev.status.value if active_rev else "no_revision",
                }
            )
    return {"sources": results}
