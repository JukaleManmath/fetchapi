from uuid import UUID

from fetch.application.queries.events import EvidenceEvent, ResultEvent, TokenEvent
from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    PgRevisionRepository,
)
from fetch.infrastructure.db.session import get_session
from fetch.mcp.dependencies import get_query_service
from fetch.mcp.server import mcp


@mcp.tool()
async def fetch_search_docs(
    source_id: str,
    query: str,
    top_k: int = 5,
) -> dict[str, object]:
    """
    Hybrid search across operations, schemas, and guides for an API source.
    Returns ranked chunks with citations and support status.
    source_id: UUID of the source from fetch_list_sources.
    query: Natural language or keyword query.
    top_k: Number of results (1-20, default 5).
    """
    settings = get_settings()
    workspace_id = settings.app.workspace_id
    src_uuid = UUID(source_id)

    async with get_session() as session:
        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get_active(src_uuid)
        if revision is None:
            return {
                "error": "NO_ACTIVE_REVISION",
                "message": "No active revision found for this source.",
            }
        revision_id = revision.id

        bundle = await get_query_service(session)
        svc = bundle.service

        answer_text = ""
        citations: list[dict[str, object]] = []
        support_status = "UNKNOWN"
        active_revision_id = str(revision_id)

        async for event in svc.stream(
            question=query,
            source_id=src_uuid,
            revision_id=revision_id,
            workspace_id=workspace_id,
        ):
            if isinstance(event, TokenEvent):
                answer_text += event.text
            elif isinstance(event, EvidenceEvent):
                citations = [
                    {
                        "source_id": c.source_id,
                        "chunk_id": str(c.chunk_id),
                        "entity_type": c.entity_type,
                        "entity_id": str(c.entity_id) if c.entity_id else None,
                        "title": c.title,
                        "method": c.method,
                        "path": c.path,
                        "source_pointer": c.source_pointer,
                    }
                    for c in event.citations
                ]
            elif isinstance(event, ResultEvent):
                support_status = event.support_status.value

    try:
        await bundle.llm_provider.aclose()
    except Exception:
        pass

    return {
        "answer": answer_text,
        "citations": citations,
        "support_status": support_status,
        "active_revision": active_revision_id,
    }
