"""Qdrant repository — collection management and chunk indexing.

Responsibilities:
- ensure_collection: idempotent collection + index setup at startup.
- upsert_chunks: batch upsert of chunk vectors and payloads.
- count_points: used by the VERIFYING stage to confirm full index coverage.
- delete_by_revision: cleanup when a revision is deleted or superseded.

Design notes (ARCHITECTURE.md §7):
- One shared collection per embedding profile version (fetch_chunks_v1).
- Tenant isolation is via payload filters (workspace_id, revision_id).
- Dense vector name: "dense". BM25 sparse is a Qdrant text index on "text".
- Point ID == chunk UUID (deterministic, no separate mapping table needed).
- Never accept raw filter objects from API callers — all filters are
  constructed server-side in this module.
"""

from __future__ import annotations

import logging
from uuid import UUID

from qdrant_client import AsyncQdrantClient
from qdrant_client.http import models as qmodels

from fetch.config import get_settings
from fetch.domain.entities import Chunk

logger = logging.getLogger(__name__)

# Payload field used for Qdrant BM25 text index. Mirrors chunk.text.
_TEXT_FIELD = "text"


class QdrantRepository:
    def __init__(self) -> None:
        settings = get_settings()
        self._client = AsyncQdrantClient(
            host=settings.qdrant.host,
            port=settings.qdrant.port,
            timeout=30,
        )
        self._collection = settings.qdrant.collection_name

    async def ensure_collection(self, dense_dimension: int) -> None:
        """Create the collection if it does not exist.

        Sets up:
        - Named dense vector with cosine distance.
        - Payload text index on the "text" field for BM25 sparse retrieval.
        - Payload keyword indexes on tenant-isolation fields.

        Idempotent — no-op if the collection already exists.
        """
        exists = await self._client.collection_exists(self._collection)
        if exists:
            logger.debug(
                "qdrant_collection_exists", extra={"collection": self._collection}
            )
            return

        await self._client.create_collection(
            collection_name=self._collection,
            vectors_config={
                "dense": qmodels.VectorParams(
                    size=dense_dimension,
                    distance=qmodels.Distance.COSINE,
                )
            },
        )

        # Text index for BM25 sparse retrieval.
        await self._client.create_payload_index(
            collection_name=self._collection,
            field_name=_TEXT_FIELD,
            field_schema=qmodels.TextIndexParams(
                type=qmodels.TextIndexType.TEXT,
                tokenizer=qmodels.TokenizerType.WORD,
                lowercase=True,
            ),
        )

        # Keyword indexes for mandatory tenant-isolation filters.
        for field in ("workspace_id", "revision_id", "source_id", "embedding_profile_version"):
            await self._client.create_payload_index(
                collection_name=self._collection,
                field_name=field,
                field_schema=qmodels.PayloadSchemaType.KEYWORD,
            )

        logger.info(
            "qdrant_collection_created",
            extra={"collection": self._collection, "dense_dimension": dense_dimension},
        )

    async def upsert_chunks(
        self,
        chunks: list[Chunk],
        vectors: list[list[float]],
        batch_size: int = 32,
    ) -> None:
        """Upsert chunks into Qdrant in bounded batches.

        vectors[i] is the dense embedding for chunks[i].
        Point ID == chunk.id (deterministic, matches qdrant_point_id).
        """
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunks ({len(chunks)}) and vectors ({len(vectors)}) length mismatch"
            )

        for batch_start in range(0, len(chunks), batch_size):
            batch_chunks = chunks[batch_start : batch_start + batch_size]
            batch_vectors = vectors[batch_start : batch_start + batch_size]

            points = [
                qmodels.PointStruct(
                    id=str(chunk.id),
                    vector={"dense": vector},
                    payload=_build_payload(chunk),
                )
                for chunk, vector in zip(batch_chunks, batch_vectors, strict=True)
            ]

            await self._client.upsert(
                collection_name=self._collection,
                points=points,
                wait=True,
            )

            logger.debug(
                "qdrant_batch_upserted",
                extra={
                    "collection": self._collection,
                    "batch_size": len(points),
                    "batch_start": batch_start,
                },
            )

    async def count_points(self, revision_id: UUID, workspace_id: UUID) -> int:
        """Count indexed points for a revision — used by the VERIFYING stage."""
        result = await self._client.count(
            collection_name=self._collection,
            count_filter=qmodels.Filter(
                must=[
                    qmodels.FieldCondition(
                        key="revision_id",
                        match=qmodels.MatchValue(value=str(revision_id)),
                    ),
                    qmodels.FieldCondition(
                        key="workspace_id",
                        match=qmodels.MatchValue(value=str(workspace_id)),
                    ),
                ]
            ),
            exact=True,
        )
        return result.count

    async def delete_by_revision(self, revision_id: UUID, workspace_id: UUID) -> None:
        """Remove all points for a revision from the collection.

        Called during source deletion (ARCHITECTURE.md §10.3).
        Never deletes the collection itself — it is shared across all sources.
        """
        await self._client.delete(
            collection_name=self._collection,
            points_selector=qmodels.FilterSelector(
                filter=qmodels.Filter(
                    must=[
                        qmodels.FieldCondition(
                            key="revision_id",
                            match=qmodels.MatchValue(value=str(revision_id)),
                        ),
                        qmodels.FieldCondition(
                            key="workspace_id",
                            match=qmodels.MatchValue(value=str(workspace_id)),
                        ),
                    ]
                )
            ),
            wait=True,
        )
        logger.info(
            "qdrant_revision_deleted",
            extra={
                "collection": self._collection,
                "revision_id": str(revision_id),
            },
        )


def _build_payload(chunk: Chunk) -> dict:
    """Build the Qdrant point payload from a Chunk.

    All fields that will ever be used as filters must be present here.
    String UUIDs are used because Qdrant keyword indexes match strings.
    """
    return {
        "workspace_id": str(chunk.workspace_id),
        "source_id": str(chunk.source_id),
        "revision_id": str(chunk.revision_id),
        "embedding_profile_version": chunk.embedding_profile_version,
        "chunk_id": str(chunk.id),
        "chunk_type": chunk.chunk_type.value,
        "entity_type": chunk.entity_type,
        "entity_id": str(chunk.entity_id),
        "title": chunk.title,
        "text": chunk.text,
        "content_hash": chunk.content_hash,
        "method": chunk.method,
        "path": chunk.path,
        "operation_id": chunk.operation_id,
        "tags": chunk.tags,
        "status_codes": chunk.status_codes,
        "api_version": chunk.api_version,
        "source_pointer": chunk.source_pointer,
        "language": chunk.language,
    }
