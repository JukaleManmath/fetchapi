"""Phase 5 — add integration_runs table.

Revision ID: 006
Revises: 005
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("language", sa.String(20), nullable=False),
        sa.Column("generated_code", sa.Text, nullable=True),
        sa.Column("validation_report", postgresql.JSONB, nullable=True),
        sa.Column("support_status", sa.String(50), nullable=False),
        sa.Column("warnings", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("context_assembly_ms", sa.Integer, nullable=True),
        sa.Column("generation_ms", sa.Integer, nullable=True),
        sa.Column("validation_ms", sa.Integer, nullable=True),
        sa.Column("total_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_runs_source", "integration_runs", ["source_id"])
    op.create_index(
        "ix_integration_runs_workspace", "integration_runs", ["workspace_id"]
    )
    op.create_index(
        "ix_integration_runs_operation", "integration_runs", ["operation_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_integration_runs_operation", table_name="integration_runs")
    op.drop_index("ix_integration_runs_workspace", table_name="integration_runs")
    op.drop_index("ix_integration_runs_source", table_name="integration_runs")
    op.drop_table("integration_runs")
