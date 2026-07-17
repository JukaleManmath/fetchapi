"""Phase 2 — embedding_profiles, chunks, chunk_relations tables.

Revision ID: 7b4c3e2f1a09
Revises: 3f8a2d1c9e47
Create Date: 2026-07-17
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "7b4c3e2f1a09"
down_revision = "3f8a2d1c9e47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── embedding_profiles ────────────────────────────────────────────────────
    # Immutable record of the exact model configuration used to produce vectors.
    # Every chunk references the profile that was active when it was embedded.
    op.create_table(
        "embedding_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("version", sa.String(50), nullable=False),
        sa.Column("dense_model_id", sa.Text, nullable=False),
        sa.Column("dense_dimension", sa.Integer, nullable=False),
        sa.Column("sparse_model_id", sa.Text, nullable=False),
        sa.Column("collection_name", sa.Text, nullable=False),
        sa.Column("distance_metric", sa.String(20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_embedding_profiles_version", "embedding_profiles", ["version"]
    )

    # ── chunks ────────────────────────────────────────────────────────────────
    # Retrieval-optimized text projections of canonical entities.
    # PostgreSQL owns the metadata; Qdrant owns the vector.
    # qdrant_point_id == id — deterministic, no separate lookup needed.
    op.create_table(
        "chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "revision_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_revisions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "embedding_profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("embedding_profiles.id"),
            nullable=False,
        ),
        sa.Column("chunk_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        # SHA-256(text + profile_version) — used for idempotency on re-ingest.
        sa.Column("content_hash", sa.String(64), nullable=False),
        # Point ID stored in Qdrant. Equals id — kept explicit for clarity.
        sa.Column("qdrant_point_id", postgresql.UUID(as_uuid=True), nullable=False),
        # Denormalized payload fields mirrored in Qdrant for filtering.
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("path", sa.Text, nullable=True),
        sa.Column("operation_id_str", sa.Text, nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("status_codes", postgresql.ARRAY(sa.Text), nullable=False),
        sa.Column("api_version", sa.Text, nullable=True),
        sa.Column("source_pointer", sa.Text, nullable=True),
        sa.Column("language", sa.Text, nullable=True),
    )
    op.create_unique_constraint(
        "uq_chunks_revision_content_hash", "chunks", ["revision_id", "content_hash"]
    )
    op.create_index("ix_chunks_revision", "chunks", ["revision_id"])
    op.create_index("ix_chunks_entity", "chunks", ["entity_type", "entity_id"])
    op.create_index("ix_chunks_workspace", "chunks", ["workspace_id"])

    # ── chunk_relations ───────────────────────────────────────────────────────
    # Typed edges used during relationship expansion after reranking.
    # Allows deterministic context addition without a second vector query.
    op.create_table(
        "chunk_relations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "from_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_chunk_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("relation_type", sa.String(50), nullable=False),
    )
    op.create_unique_constraint(
        "uq_chunk_relations_edge",
        "chunk_relations",
        ["from_chunk_id", "to_chunk_id", "relation_type"],
    )
    op.create_index("ix_chunk_relations_from", "chunk_relations", ["from_chunk_id"])
    op.create_index("ix_chunk_relations_revision", "chunk_relations", ["revision_id"])


def downgrade() -> None:
    op.drop_table("chunk_relations")
    op.drop_table("chunks")
    op.drop_table("embedding_profiles")
