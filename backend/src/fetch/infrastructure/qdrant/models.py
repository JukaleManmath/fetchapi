"""Shared value objects for the Qdrant infrastructure layer."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ChunkHit:
    """A single result returned by a Qdrant vector search.

    ``payload`` is the raw Qdrant point payload forwarded as-is so that
    downstream retrieval stages (reranker, citation builder) can access
    all indexed fields without an additional database round-trip.
    """

    chunk_id: UUID
    score: float
    payload: dict[str, Any]
