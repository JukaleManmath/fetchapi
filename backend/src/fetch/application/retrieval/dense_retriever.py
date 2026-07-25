"""Dense retrieval stage.

Embeds the query using the EmbeddingProvider with input_type="query" and
performs a tenant-scoped dense vector search against Qdrant.

The application layer depends on domain protocols (EmbeddingProvider) and the
Qdrant infrastructure type directly, which is acceptable because QdrantRepository
is internal infrastructure — not a third-party provider that would ever be swapped.
ChunkHit is imported from the infrastructure layer because it is the value object
produced by Qdrant and consumed directly by downstream retrieval stages (reranker).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from fetch.domain.protocols import EmbeddingProvider
from fetch.infrastructure.qdrant.models import ChunkHit
from fetch.infrastructure.qdrant.repository import QdrantRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DenseRetrievalConfig:
    """Immutable configuration for a single dense retrieval call."""

    model_id: str
    top_k: int = 25
    embedding_profile_version: str = "v1"


class DenseRetriever:
    """Embeds a query and retrieves the top-k dense matches from Qdrant.

    This class is stateless beyond its injected dependencies; a single
    instance can be shared across concurrent requests.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        qdrant: QdrantRepository,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._qdrant = qdrant

    async def retrieve(
        self,
        query_text: str,
        revision_id: UUID,
        workspace_id: UUID,
        config: DenseRetrievalConfig,
        source_ids: list[UUID] | None = None,
    ) -> list[ChunkHit]:
        """Embed ``query_text`` and return the top-k tenant-scoped chunk hits.

        Steps:
        1. Embed the query with input_type="query" (asymmetric NIM convention).
        2. Call Qdrant search_dense with mandatory tenant filters.
        3. Return the ChunkHit list sorted by descending score (Qdrant order).
        """
        embedding_results = await self._embedding_provider.embed(
            [query_text],
            model_id=config.model_id,
            input_type="query",
        )

        if not embedding_results:
            logger.warning(
                "dense_retriever_empty_embedding",
                extra={"revision_id": str(revision_id)},
            )
            return []

        query_vector = embedding_results[0].vector

        hits = await self._qdrant.search_dense(
            query_vector=query_vector,
            revision_id=revision_id,
            workspace_id=workspace_id,
            embedding_profile_version=config.embedding_profile_version,
            top_k=config.top_k,
            source_ids=source_ids,
        )

        logger.debug(
            "dense_retriever_complete",
            extra={
                "revision_id": str(revision_id),
                "workspace_id": str(workspace_id),
                "top_k": config.top_k,
                "hits": len(hits),
            },
        )

        return hits
