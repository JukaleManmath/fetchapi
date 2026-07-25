"""BM25 (lexical) retrieval stage.

Performs a full-text search against the Qdrant text payload index and returns
tenant-scoped ChunkHit objects.  No embedding call is required — the query text
is forwarded directly to the Qdrant text index.

Score note: Qdrant's scroll-based text filter does not produce per-document
BM25 scores.  Every returned hit carries score=1.0.  A downstream reranker is
expected to assign calibrated scores before results are presented to the user.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from fetch.infrastructure.qdrant.models import ChunkHit
from fetch.infrastructure.qdrant.repository import QdrantRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BM25RetrievalConfig:
    """Immutable configuration for a single BM25 retrieval call."""

    top_k: int = 25
    embedding_profile_version: str = "v1"


class BM25Retriever:
    """Performs lexical retrieval against the Qdrant text index.

    This class is stateless beyond its injected dependency; a single instance
    can be shared across concurrent requests.
    """

    def __init__(self, qdrant: QdrantRepository) -> None:
        self._qdrant = qdrant

    async def retrieve(
        self,
        query_text: str,
        revision_id: UUID,
        workspace_id: UUID,
        config: BM25RetrievalConfig,
        source_ids: list[UUID] | None = None,
    ) -> list[ChunkHit]:
        """Return top-k lexically matching chunks for ``query_text``.

        Delegates entirely to QdrantRepository.search_bm25; all tenant
        isolation is enforced there.
        """
        hits = await self._qdrant.search_bm25(
            query_text=query_text,
            revision_id=revision_id,
            workspace_id=workspace_id,
            embedding_profile_version=config.embedding_profile_version,
            top_k=config.top_k,
            source_ids=source_ids,
        )

        logger.debug(
            "bm25_retriever_complete",
            extra={
                "revision_id": str(revision_id),
                "workspace_id": str(workspace_id),
                "top_k": config.top_k,
                "hits": len(hits),
            },
        )

        return hits
