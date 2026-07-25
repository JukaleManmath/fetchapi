"""Phase 3 — query_runs table for retrieval traces and query history.

Revision ID: 2c9d4b1e8f03
Revises: 9c1d4a7e3b82
Create Date: 2026-07-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "2c9d4b1e8f03"
down_revision = "9c1d4a7e3b82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "query_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workflow", sa.String(50), nullable=False),
        sa.Column("question", sa.Text, nullable=False),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("citations", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("support_status", sa.String(50), nullable=False),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("retrieval_ms", sa.Integer, nullable=True),
        sa.Column("generation_ms", sa.Integer, nullable=True),
        sa.Column("total_ms", sa.Integer, nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        # Retrieval trace fields
        sa.Column("dense_candidate_count", sa.Integer, nullable=True),
        sa.Column("bm25_candidate_count", sa.Integer, nullable=True),
        sa.Column("fused_candidate_count", sa.Integer, nullable=True),
        sa.Column("reranked_candidate_count", sa.Integer, nullable=True),
        sa.Column("expanded_candidate_count", sa.Integer, nullable=True),
        sa.Column(
            "exact_match_found", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_query_runs_source", "query_runs", ["source_id"])
    op.create_index("ix_query_runs_workspace", "query_runs", ["workspace_id"])
    op.create_index(
        "ix_query_runs_created_at", "query_runs", ["source_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_query_runs_created_at", table_name="query_runs")
    op.drop_index("ix_query_runs_workspace", table_name="query_runs")
    op.drop_index("ix_query_runs_source", table_name="query_runs")
    op.drop_table("query_runs")
