"""Initial schema — all Phase 1 tables.

Revision ID: 3f8a2d1c9e47
Revises:
Create Date: 2026-07-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "3f8a2d1c9e47"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── workspaces ────────────────────────────────────────────────────────────
    op.create_table(
        "workspaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── api_sources ───────────────────────────────────────────────────────────
    op.create_table(
        "api_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("config_url", sa.Text, nullable=True),
        sa.Column("config_object_key", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_api_sources_workspace", "api_sources", ["workspace_id"])

    # ── source_revisions ──────────────────────────────────────────────────────
    op.create_table(
        "source_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=True),
        sa.Column("snapshot_object_key", sa.Text, nullable=True),
        sa.Column("api_version", sa.String(100), nullable=True),
        sa.Column("api_title", sa.String(255), nullable=True),
        sa.Column("expected_chunk_count", sa.Integer, nullable=True),
        sa.Column("actual_chunk_count", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["api_sources.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_source_revisions_source_status", "source_revisions", ["source_id", "status"]
    )
    op.create_index("ix_source_revisions_workspace", "source_revisions", ["workspace_id"])

    # ── ingestion_jobs ────────────────────────────────────────────────────────
    op.create_table(
        "ingestion_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", sa.String(50), nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["api_sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_ingestion_jobs_revision", "ingestion_jobs", ["revision_id"])
    op.create_index("ix_ingestion_jobs_source", "ingestion_jobs", ["source_id"])

    # ── api_servers ───────────────────────────────────────────────────────────
    op.create_table(
        "api_servers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "variables", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_api_servers_revision", "api_servers", ["revision_id"])

    # ── api_operations ────────────────────────────────────────────────────────
    op.create_table(
        "api_operations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("path_normalized", sa.Text, nullable=False),
        sa.Column("operation_id", sa.String(255), nullable=True),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("deprecated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("logical_key", sa.Text, nullable=False),
        sa.Column("source_pointer", sa.Text, nullable=True),
        sa.Column(
            "security_requirements",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="[]",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "revision_id", "logical_key", name="uq_operations_revision_logical_key"
        ),
    )
    op.create_index("ix_api_operations_revision", "api_operations", ["revision_id"])
    op.create_index(
        "ix_api_operations_lookup",
        "api_operations",
        ["revision_id", "path_normalized", "method"],
    )

    # ── api_parameters ────────────────────────────────────────────────────────
    op.create_table(
        "api_parameters",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location", sa.String(20), nullable=False),
        sa.Column("required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deprecated", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("schema_json", sa.Text, nullable=True),
        sa.Column("example_json", sa.Text, nullable=True),
        sa.Column("source_pointer", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["api_operations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_api_parameters_operation", "api_parameters", ["operation_id"])

    # ── api_request_bodies ────────────────────────────────────────────────────
    op.create_table(
        "api_request_bodies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("required", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "content_schemas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["api_operations.id"], ondelete="CASCADE"
        ),
    )

    # ── api_responses ─────────────────────────────────────────────────────────
    op.create_table(
        "api_responses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status_code", sa.String(10), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column(
            "content_schemas",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "headers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["api_operations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_api_responses_operation", "api_responses", ["operation_id"])

    # ── api_schemas ───────────────────────────────────────────────────────────
    op.create_table(
        "api_schemas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("schema_json", sa.Text, nullable=False),
        sa.Column("source_pointer", sa.Text, nullable=True),
        sa.Column("logical_key", sa.Text, nullable=False),
        sa.Column("nullable", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("deprecated", sa.Boolean, nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "revision_id", "logical_key", name="uq_schemas_revision_logical_key"
        ),
    )
    op.create_index("ix_api_schemas_revision", "api_schemas", ["revision_id"])

    # ── auth_schemes ──────────────────────────────────────────────────────────
    op.create_table(
        "auth_schemes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("scheme_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("details_json", sa.Text, nullable=False),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("revision_id", "name", name="uq_auth_schemes_revision_name"),
    )
    op.create_index("ix_auth_schemes_revision", "auth_schemes", ["revision_id"])

    # ── api_examples ──────────────────────────────────────────────────────────
    op.create_table(
        "api_examples",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_pointer", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_api_examples_revision", "api_examples", ["revision_id"])

    # ── error_definitions ─────────────────────────────────────────────────────
    op.create_table(
        "error_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("revision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status_code", sa.String(10), nullable=True),
        sa.Column("error_code", sa.String(255), nullable=True),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("source_pointer", sa.Text, nullable=True),
        sa.ForeignKeyConstraint(
            ["revision_id"], ["source_revisions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index("ix_error_definitions_revision", "error_definitions", ["revision_id"])


def downgrade() -> None:
    op.drop_table("error_definitions")
    op.drop_table("api_examples")
    op.drop_table("auth_schemes")
    op.drop_table("api_schemas")
    op.drop_table("api_responses")
    op.drop_table("api_request_bodies")
    op.drop_table("api_parameters")
    op.drop_table("api_operations")
    op.drop_table("api_servers")
    op.drop_table("ingestion_jobs")
    op.drop_table("source_revisions")
    op.drop_table("api_sources")
    op.drop_table("workspaces")
