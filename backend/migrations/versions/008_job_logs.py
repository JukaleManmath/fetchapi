"""Add job_logs table for structured ingestion stage logs.

Revision ID: 008
Revises: 007
Create Date: 2026-07-26
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.String(50), nullable=True),
        sa.Column("level", sa.String(20), nullable=False, server_default="info"),
        sa.Column("message", sa.String(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["ingestion_jobs.id"],
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_job_logs_job", "job_logs", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_job_logs_job", table_name="job_logs")
    op.drop_table("job_logs")
