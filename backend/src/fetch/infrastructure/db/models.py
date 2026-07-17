"""SQLAlchemy 2.x ORM models.

Infrastructure-layer only. Domain/application code maps between these and
domain entities — ORM objects never cross a layer boundary.

All timestamps: UTC, timezone-aware.
All IDs: UUID.
JSON fields: JSONB for efficient PostgreSQL querying.
Large text fields (schema_json, details_json): Text.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Workspace ─────────────────────────────────────────────────────────────────


class WorkspaceModel(Base):
    __tablename__ = "workspaces"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sources: Mapped[list["ApiSourceModel"]] = relationship(back_populates="workspace")


# ── Source and revision ───────────────────────────────────────────────────────


class ApiSourceModel(Base):
    __tablename__ = "api_sources"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    workspace_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    config_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    workspace: Mapped["WorkspaceModel"] = relationship(back_populates="sources")
    revisions: Mapped[list["SourceRevisionModel"]] = relationship(back_populates="source")

    __table_args__ = (Index("ix_api_sources_workspace", "workspace_id"),)


class SourceRevisionModel(Base):
    __tablename__ = "source_revisions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snapshot_object_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    api_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expected_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_chunk_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped["ApiSourceModel"] = relationship(back_populates="revisions")
    jobs: Mapped[list["IngestionJobModel"]] = relationship(back_populates="revision")
    operations: Mapped[list["ApiOperationModel"]] = relationship(back_populates="revision")
    schemas: Mapped[list["ApiSchemaModel"]] = relationship(back_populates="revision")
    auth_schemes: Mapped[list["AuthSchemeModel"]] = relationship(back_populates="revision")
    servers: Mapped[list["ApiServerModel"]] = relationship(back_populates="revision")
    examples: Mapped[list["ApiExampleModel"]] = relationship(back_populates="revision")
    error_definitions: Mapped[list["ErrorDefinitionModel"]] = relationship(
        back_populates="revision"
    )

    __table_args__ = (
        Index("ix_source_revisions_source_status", "source_id", "status"),
        Index("ix_source_revisions_workspace", "workspace_id"),
    )


# ── Ingestion job ─────────────────────────────────────────────────────────────


class IngestionJobModel(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_sources.id", ondelete="CASCADE"),
        nullable=False,
    )
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="jobs")

    __table_args__ = (
        Index("ix_ingestion_jobs_revision", "revision_id"),
        Index("ix_ingestion_jobs_source", "source_id"),
    )


# ── API server ────────────────────────────────────────────────────────────────


class ApiServerModel(Base):
    __tablename__ = "api_servers"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. {"environment": {"default": "production", "enum": ["production", "sandbox"]}}
    variables: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="servers")

    __table_args__ = (Index("ix_api_servers_revision", "revision_id"),)


# ── Canonical API entities ────────────────────────────────────────────────────


class ApiOperationModel(Base):
    __tablename__ = "api_operations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    path_normalized: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # {source_id}:{api_version}:{METHOD}:{path_normalized}
    logical_key: Mapped[str] = mapped_column(Text, nullable=False)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # list of dicts: [{"bearerAuth": []}, {"apiKey": ["read"]}]
    security_requirements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="operations")
    parameters: Mapped[list["ApiParameterModel"]] = relationship(
        back_populates="operation", cascade="all, delete-orphan"
    )
    request_body: Mapped["ApiRequestBodyModel | None"] = relationship(
        back_populates="operation", cascade="all, delete-orphan", uselist=False
    )
    responses: Mapped[list["ApiResponseModel"]] = relationship(
        back_populates="operation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "revision_id", "logical_key", name="uq_operations_revision_logical_key"
        ),
        Index("ix_api_operations_revision", "revision_id"),
        Index("ix_api_operations_lookup", "revision_id", "path_normalized", "method"),
    )


class ApiParameterModel(Base):
    __tablename__ = "api_parameters"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_operations.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str] = mapped_column(String(20), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)

    operation: Mapped["ApiOperationModel | None"] = relationship(back_populates="parameters")

    __table_args__ = (Index("ix_api_parameters_operation", "operation_id"),)


class ApiRequestBodyModel(Base):
    __tablename__ = "api_request_bodies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_operations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # one request body per operation
    )
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"application/json": "{...schema...}", "multipart/form-data": "{...}"}
    content_schemas: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    operation: Mapped["ApiOperationModel"] = relationship(back_populates="request_body")


class ApiResponseModel(Base):
    __tablename__ = "api_responses"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    operation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("api_operations.id", ondelete="CASCADE"),
        nullable=False,
    )
    status_code: Mapped[str] = mapped_column(String(10), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_schemas: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    headers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    operation: Mapped["ApiOperationModel"] = relationship(back_populates="responses")

    __table_args__ = (Index("ix_api_responses_operation", "operation_id"),)


class ApiSchemaModel(Base):
    __tablename__ = "api_schemas"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {source_id}:{api_version}:{source_pointer_or_name}
    logical_key: Mapped[str] = mapped_column(Text, nullable=False)
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deprecated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="schemas")

    __table_args__ = (
        UniqueConstraint("revision_id", "logical_key", name="uq_schemas_revision_logical_key"),
        Index("ix_api_schemas_revision", "revision_id"),
    )


class AuthSchemeModel(Base):
    __tablename__ = "auth_schemes"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    scheme_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # scheme-specific JSON: {"in": "header", "name": "X-API-Key"} or {"flows": {...}}
    details_json: Mapped[str] = mapped_column(Text, nullable=False)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="auth_schemes")

    __table_args__ = (
        UniqueConstraint("revision_id", "name", name="uq_auth_schemes_revision_name"),
        Index("ix_auth_schemes_revision", "revision_id"),
    )


class ApiExampleModel(Base):
    __tablename__ = "api_examples"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="examples")

    __table_args__ = (Index("ix_api_examples_revision", "revision_id"),)


class ErrorDefinitionModel(Base):
    __tablename__ = "error_definitions"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    operation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)

    revision: Mapped["SourceRevisionModel"] = relationship(back_populates="error_definitions")

    __table_args__ = (Index("ix_error_definitions_revision", "revision_id"),)


# ── Embedding profile ─────────────────────────────────────────────────────────


class EmbeddingProfileModel(Base):
    __tablename__ = "embedding_profiles"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    # Human-readable version string, e.g. "v1". Unique — one profile per version.
    version: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    dense_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    dense_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    sparse_model_id: Mapped[str] = mapped_column(Text, nullable=False)
    collection_name: Mapped[str] = mapped_column(Text, nullable=False)
    distance_metric: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    chunks: Mapped[list["ChunkModel"]] = relationship(back_populates="embedding_profile")


# ── Chunks ────────────────────────────────────────────────────────────────────


class ChunkModel(Base):
    __tablename__ = "chunks"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("source_revisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    embedding_profile_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("embedding_profiles.id"),
        nullable=False,
    )
    chunk_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # SHA-256(text + profile_version) — idempotency key for re-ingestion.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    # Equals id — deterministic Qdrant point ID, stored explicitly for clarity.
    qdrant_point_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    # Denormalized payload fields mirrored in Qdrant for filtering.
    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_id_str: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    status_codes: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list)
    api_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_pointer: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedding_profile: Mapped["EmbeddingProfileModel"] = relationship(back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("revision_id", "content_hash", name="uq_chunks_revision_content_hash"),
        Index("ix_chunks_revision", "revision_id"),
        Index("ix_chunks_entity", "entity_type", "entity_id"),
        Index("ix_chunks_workspace", "workspace_id"),
    )


# ── Chunk relations ───────────────────────────────────────────────────────────


class ChunkRelationModel(Base):
    __tablename__ = "chunk_relations"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True)
    revision_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    from_chunk_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_chunk_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("chunks.id", ondelete="CASCADE"),
        nullable=False,
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "from_chunk_id", "to_chunk_id", "relation_type",
            name="uq_chunk_relations_edge",
        ),
        Index("ix_chunk_relations_from", "from_chunk_id"),
        Index("ix_chunk_relations_revision", "revision_id"),
    )
