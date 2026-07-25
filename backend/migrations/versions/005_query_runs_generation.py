"""Phase 4 — add intent_classification and prompt_version to query_runs.

Revision ID: 005
Revises: 2c9d4b1e8f03
Create Date: 2026-07-24
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "2c9d4b1e8f03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "query_runs",
        sa.Column("intent_classification", sa.String(50), nullable=True),
    )
    op.add_column(
        "query_runs",
        sa.Column("prompt_version", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("query_runs", "prompt_version")
    op.drop_column("query_runs", "intent_classification")
