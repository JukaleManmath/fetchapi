"""Embedding profile management.

An EmbeddingProfile is an immutable record that captures the exact model
configuration used to produce vectors for a set of chunks. It is persisted
to PostgreSQL so that any chunk can be traced back to the configuration
that produced its embedding — essential for evaluation and ablation runs.

Every ingestion session uses exactly one profile. If a profile with the
configured version already exists it is reused; the settings are not
re-validated against the stored record (the version string is the contract).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from fetch.config import get_settings
from fetch.infrastructure.db.repositories import (
    EmbeddingProfileRecord,
    PgEmbeddingProfileRepository,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmbeddingProfile:
    """Resolved embedding profile used during a single ingestion run.

    Carries both the DB record ID (for FK references on chunks) and the
    config values needed by the Qdrant repository to set up the collection.
    """

    id: UUID
    version: str
    dense_model_id: str
    dense_dimension: int
    sparse_model_id: str
    collection_name: str
    distance_metric: str


async def get_or_create_profile(session: AsyncSession) -> EmbeddingProfile:
    """Return the active embedding profile, creating it in the DB if absent.

    The profile version is derived from settings. If a row for that version
    already exists it is returned as-is — the record is immutable.
    """
    settings = get_settings()
    version = "v1"  # Bump to "v2" when any incompatible field changes.

    repo = PgEmbeddingProfileRepository(session)
    existing = await repo.get_by_version(version)

    if existing is not None:
        logger.debug(
            "embedding_profile_reused",
            extra={"version": version, "profile_id": str(existing.id)},
        )
        return _to_profile(existing)

    record = EmbeddingProfileRecord(
        id=uuid4(),
        version=version,
        dense_model_id=settings.embeddings.model_id,
        dense_dimension=settings.embeddings.dimension,
        sparse_model_id="Qdrant/bm25",
        collection_name=settings.qdrant.collection_name,
        distance_metric="cosine",
        created_at=datetime.now(UTC),
    )
    await repo.save(record)

    # Re-fetch to handle the case where a concurrent ingestion already inserted it.
    created = await repo.get_by_version(version)
    if created is None:
        # Should never happen — just inserted above.
        raise RuntimeError(f"Embedding profile {version!r} missing after insert.")

    logger.info(
        "embedding_profile_created",
        extra={
            "version": version,
            "profile_id": str(created.id),
            "dense_model_id": created.dense_model_id,
            "dense_dimension": created.dense_dimension,
        },
    )
    return _to_profile(created)


def _to_profile(record: EmbeddingProfileRecord) -> EmbeddingProfile:
    return EmbeddingProfile(
        id=record.id,
        version=record.version,
        dense_model_id=record.dense_model_id,
        dense_dimension=record.dense_dimension,
        sparse_model_id=record.sparse_model_id,
        collection_name=record.collection_name,
        distance_metric=record.distance_metric,
    )
