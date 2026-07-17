"""Seed the default single-tenant workspace.

The default workspace ID matches AppSettings.workspace_id so that the
Phase 1–2 hardcoded single-tenant path satisfies the FK constraint on
api_sources.workspace_id.

Revision ID: 9c1d4a7e3b82
Revises: 7b4c3e2f1a09
Create Date: 2026-07-17
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "9c1d4a7e3b82"
down_revision = "7b4c3e2f1a09"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO workspaces (id, name, created_at) "
            "VALUES (CAST(:id AS uuid), :name, :created_at) "
            "ON CONFLICT (id) DO NOTHING"
        ).bindparams(
            id=DEFAULT_WORKSPACE_ID,
            name="default",
            created_at=datetime.now(UTC),
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)").bindparams(
            id=DEFAULT_WORKSPACE_ID,
        )
    )
