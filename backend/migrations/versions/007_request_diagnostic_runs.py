"""Phase 6 — add request_diagnostic_runs table.

Revision ID: 007
Revises: 006
Create Date: 2026-07-25
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_diagnostic_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("input_type", sa.String(20), nullable=False),
        sa.Column("raw_input", sa.Text, nullable=False),
        sa.Column("parsed_method", sa.String(10), nullable=True),
        sa.Column("parsed_url", sa.Text, nullable=True),
        sa.Column("received_status_code", sa.String(10), nullable=True),
        sa.Column("diagnostic", postgresql.JSONB, nullable=True),
        sa.Column("explanation", sa.Text, nullable=True),
        sa.Column("corrected_curl", sa.Text, nullable=True),
        sa.Column("is_valid", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("support_status", sa.String(50), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=True),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("parse_ms", sa.Integer, nullable=True),
        sa.Column("match_ms", sa.Integer, nullable=True),
        sa.Column("validate_ms", sa.Integer, nullable=True),
        sa.Column("explanation_ms", sa.Integer, nullable=True),
        sa.Column("total_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_diagnostic_runs_source", "request_diagnostic_runs", ["source_id"])
    op.create_index("ix_diagnostic_runs_workspace", "request_diagnostic_runs", ["workspace_id"])
    op.create_index("ix_diagnostic_runs_operation", "request_diagnostic_runs", ["operation_id"])


def downgrade() -> None:
    op.drop_index("ix_diagnostic_runs_operation", table_name="request_diagnostic_runs")
    op.drop_index("ix_diagnostic_runs_workspace", table_name="request_diagnostic_runs")
    op.drop_index("ix_diagnostic_runs_source", table_name="request_diagnostic_runs")
    op.drop_table("request_diagnostic_runs")
