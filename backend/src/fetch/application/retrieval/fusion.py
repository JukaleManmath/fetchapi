"""Reciprocal Rank Fusion (RRF) for hybrid retrieval.

Merges N independently ranked ChunkHit lists into a single fused list.
No external dependencies; pure Python.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fetch.infrastructure.qdrant.models import ChunkHit


@dataclass(frozen=True)
class FusionConfig:
    """Immutable parameters for a single RRF fusion call."""

    k: int = 60  # RRF constant — prevents top-rank results from dominating
    top_k: int = 30  # maximum candidates to return after fusion


class RRFFusion:
    """Merges N ranked ChunkHit lists with Reciprocal Rank Fusion.

    Stateless — a single instance can be reused across requests.
    """

    def fuse(
        self,
        ranked_lists: list[list[ChunkHit]],
        config: FusionConfig | None = None,
    ) -> list[ChunkHit]:
        """Merge N ranked ChunkHit lists with RRF.

        Returns at most config.top_k hits, sorted by descending fused score.
        The returned ChunkHit.score is the RRF score (not original retrieval score).
        The returned ChunkHit.payload is taken from the first list that contained
        the doc (i.e. the first list in ranked_lists order that has that chunk_id).
        """
        if config is None:
            config = FusionConfig()

        # Accumulate RRF scores keyed by chunk_id.
        scores: dict[UUID, float] = {}
        # Payload from the first encounter (first list, first rank).
        payloads: dict[UUID, dict[str, Any]] = {}

        for ranked in ranked_lists:
            for rank_zero, hit in enumerate(ranked):
                rank = rank_zero + 1  # 1-indexed
                contribution = 1.0 / (config.k + rank)
                scores[hit.chunk_id] = scores.get(hit.chunk_id, 0.0) + contribution
                if hit.chunk_id not in payloads:
                    payloads[hit.chunk_id] = hit.payload

        if not scores:
            return []

        fused = sorted(scores.items(), key=lambda item: item[1], reverse=True)

        return [
            ChunkHit(
                chunk_id=chunk_id,
                score=score,
                payload=payloads[chunk_id],
            )
            for chunk_id, score in fused[: config.top_k]
        ]
