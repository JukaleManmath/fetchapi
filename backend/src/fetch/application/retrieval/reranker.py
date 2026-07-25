"""Cross-encoder reranking stage.

Takes a list of ChunkHit candidates (e.g. from RRF fusion) and reranks them
using a RerankProvider. The returned ChunkHit.score is replaced with the
reranker score; all other fields (chunk_id, payload) are preserved.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from fetch.domain.protocols import RerankCandidate, RerankProvider
from fetch.infrastructure.qdrant.models import ChunkHit

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RerankConfig:
    """Immutable parameters for a single reranking call."""

    model_id: str
    top_n: int = 10  # candidates to keep after reranking (ARCHITECTURE.md §11.2: 8-12)


class RetrievalReranker:
    """Reranks ChunkHit candidates using a cross-encoder provider.

    Stateless beyond the injected provider — a single instance can be reused
    across requests.
    """

    def __init__(self, rerank_provider: RerankProvider) -> None:
        self._provider = rerank_provider

    async def rerank(
        self,
        query: str,
        candidates: list[ChunkHit],
        config: RerankConfig,
    ) -> list[ChunkHit]:
        """Rerank ChunkHit candidates using the cross-encoder provider.

        Returns at most config.top_n hits sorted by descending reranker score.
        ChunkHit.score is replaced with the reranker score; chunk_id and payload
        are preserved from the input hit.

        If candidates is empty, returns [] without calling the provider.
        """
        if not candidates:
            return []

        rerank_candidates = [
            RerankCandidate(index=i, text=hit.payload.get("text", ""))
            for i, hit in enumerate(candidates)
        ]

        results = await self._provider.rerank(
            query=query,
            candidates=rerank_candidates,
            model_id=config.model_id,
            top_n=config.top_n,
        )

        logger.debug(
            "reranker returned %d results from %d candidates (top_n=%d)",
            len(results),
            len(candidates),
            config.top_n,
        )

        return [
            ChunkHit(
                chunk_id=candidates[result.index].chunk_id,
                score=result.score,
                payload=candidates[result.index].payload,
            )
            for result in results
        ]
