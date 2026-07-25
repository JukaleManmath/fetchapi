"""Relationship expansion stage.

After reranking, deterministically adds related chunks to the result set
by following ChunkRelation edges stored in PostgreSQL. No additional
semantic retrieval is performed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from fetch.domain.entities import Chunk
from fetch.domain.enums import ChunkRelationType
from fetch.domain.protocols import ChunkRelationRepository, ChunkRepository
from fetch.infrastructure.qdrant.models import ChunkHit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExpansionConfig:
    """Immutable parameters for a single expansion call."""

    max_expanded_chunks: int = 5
    # None means all relation types are followed.
    relation_types: list[ChunkRelationType] | None = field(default=None)


def _chunk_to_payload(chunk: Chunk) -> dict[str, object]:
    return {
        "text": chunk.text,
        "title": chunk.title,
        "entity_type": chunk.entity_type,
        "chunk_type": chunk.chunk_type.value,
        "method": chunk.method,
        "path": chunk.path,
    }


class RelationshipExpander:
    """Adds related chunks deterministically after reranking.

    Stateless beyond the injected repositories — a single instance can be
    reused across requests.
    """

    def __init__(
        self,
        relation_repo: ChunkRelationRepository,
        chunk_repo: ChunkRepository,
    ) -> None:
        self._relation_repo = relation_repo
        self._chunk_repo = chunk_repo

    async def expand(
        self,
        hits: list[ChunkHit],
        revision_id: UUID,
        config: ExpansionConfig | None = None,
    ) -> list[ChunkHit]:
        """Append related chunks to the reranked hit list.

        Returns the original hits first, followed by up to
        config.max_expanded_chunks additional ChunkHit objects built from
        ChunkRelation edges. Expanded hits have score=0.0 and a minimal
        payload derived from the Chunk entity. Chunks already present in
        hits are never added again.
        """
        if config is None:
            config = ExpansionConfig()

        if not hits:
            return hits

        existing_ids: set[UUID] = {h.chunk_id for h in hits}

        chunk_ids = list(existing_ids)
        relations = await self._relation_repo.find_relations_for_chunks(
            chunk_ids=chunk_ids, revision_id=revision_id
        )

        if not relations:
            return hits

        # Filter by relation_types if specified.
        if config.relation_types is not None:
            allowed = set(config.relation_types)
            relations = [r for r in relations if r.relation_type in allowed]

        # Collect candidate to_chunk_ids not already in hits.
        candidate_ids: list[UUID] = []
        seen: set[UUID] = set(existing_ids)
        for rel in relations:
            if rel.to_chunk_id not in seen:
                candidate_ids.append(rel.to_chunk_id)
                seen.add(rel.to_chunk_id)

        if not candidate_ids:
            return hits

        # Apply cap before the DB fetch.
        candidate_ids = candidate_ids[: config.max_expanded_chunks]

        chunks = await self._chunk_repo.find_chunks_by_ids(candidate_ids)

        expanded: list[ChunkHit] = [
            ChunkHit(
                chunk_id=chunk.id,
                score=0.0,
                payload=_chunk_to_payload(chunk),
            )
            for chunk in chunks
        ]

        logger.debug(
            "relationship_expansion added %d chunks from %d relations",
            len(expanded),
            len(relations),
        )

        return hits + expanded
