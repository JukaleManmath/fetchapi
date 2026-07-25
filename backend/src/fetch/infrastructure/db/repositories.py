"""Concrete async SQLAlchemy repository implementations.

Each class implements a domain protocol from domain/protocols.py.
ORM models are never returned — they are mapped to domain entities here.
All methods receive an AsyncSession injected from the caller.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from fetch.domain.entities import (
    ApiExample,
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    ApiResponse,
    ApiSchema,
    ApiServer,
    ApiSource,
    AuthScheme,
    Chunk,
    ChunkRelation,
    Citation,
    DiagnosticFinding,
    EndpointMatch,
    ErrorDefinition,
    ErrorStatusMatch,
    IngestionJob,
    IntegrationRun,
    ParsedRequest,
    QueryRun,
    RequestDiagnostic,
    RequestDiagnosticRun,
    SourceRevision,
    ValidationIssue,
    ValidationReport,
)
from fetch.domain.enums import (
    AuthSchemeType,
    ChunkType,
    DiagnosticCategory,
    DiagnosticInputType,
    GenerationLanguage,
    HttpMethod,
    IngestionStage,
    MatchConfidence,
    ParameterLocation,
    QueryWorkflow,
    RevisionStatus,
    SourceType,
    SupportStatus,
)
from fetch.infrastructure.db.models import (
    ApiExampleModel,
    ApiOperationModel,
    ApiParameterModel,
    ApiRequestBodyModel,
    ApiResponseModel,
    ApiSchemaModel,
    ApiServerModel,
    ApiSourceModel,
    AuthSchemeModel,
    ChunkModel,
    ChunkRelationModel,
    EmbeddingProfileModel,
    ErrorDefinitionModel,
    IngestionJobModel,
    IntegrationRunModel,
    QueryRunModel,
    RequestDiagnosticRunModel,
    SourceRevisionModel,
)

logger = logging.getLogger(__name__)


# ── Mappers (ORM → domain) ────────────────────────────────────────────────────


def _map_source(row: ApiSourceModel) -> ApiSource:
    return ApiSource(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        source_type=SourceType(row.source_type),
        config_url=row.config_url,
        config_object_key=row.config_object_key,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _map_revision(row: SourceRevisionModel) -> SourceRevision:
    return SourceRevision(
        id=row.id,
        source_id=row.source_id,
        workspace_id=row.workspace_id,
        status=RevisionStatus(row.status),
        content_hash=row.content_hash,
        snapshot_object_key=row.snapshot_object_key,
        api_version=row.api_version,
        api_title=row.api_title,
        expected_chunk_count=row.expected_chunk_count,
        actual_chunk_count=row.actual_chunk_count,
        created_at=row.created_at,
        activated_at=row.activated_at,
        failed_at=row.failed_at,
        failure_reason=row.failure_reason,
    )


def _map_job(row: IngestionJobModel) -> IngestionJob:
    return IngestionJob(
        id=row.id,
        source_id=row.source_id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        stage=IngestionStage(row.stage),
        attempt=row.attempt,
        max_attempts=row.max_attempts,
        error_message=row.error_message,
        created_at=row.created_at,
        updated_at=row.updated_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
    )


# ── SourceRepository ──────────────────────────────────────────────────────────


class PgSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, source_id: UUID) -> ApiSource | None:
        row = await self._session.get(ApiSourceModel, source_id)
        return _map_source(row) if row else None

    async def list_by_workspace(self, workspace_id: UUID) -> list[ApiSource]:
        result = await self._session.execute(
            select(ApiSourceModel).where(ApiSourceModel.workspace_id == workspace_id)
        )
        return [_map_source(r) for r in result.scalars().all()]

    async def save(self, source: ApiSource) -> None:
        row = await self._session.get(ApiSourceModel, source.id)
        if row is None:
            self._session.add(
                ApiSourceModel(
                    id=source.id,
                    workspace_id=source.workspace_id,
                    name=source.name,
                    source_type=source.source_type.value,
                    config_url=source.config_url,
                    config_object_key=source.config_object_key,
                    created_at=source.created_at,
                    updated_at=source.updated_at,
                )
            )
        else:
            row.name = source.name
            row.config_url = source.config_url
            row.config_object_key = source.config_object_key
            row.updated_at = source.updated_at


# ── RevisionRepository ────────────────────────────────────────────────────────


class PgRevisionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, revision_id: UUID) -> SourceRevision | None:
        row = await self._session.get(SourceRevisionModel, revision_id)
        return _map_revision(row) if row else None

    async def get_active(self, source_id: UUID) -> SourceRevision | None:
        result = await self._session.execute(
            select(SourceRevisionModel).where(
                SourceRevisionModel.source_id == source_id,
                SourceRevisionModel.status == RevisionStatus.ACTIVE.value,
            )
        )
        row = result.scalar_one_or_none()
        return _map_revision(row) if row else None

    async def get_by_content_hash(
        self, source_id: UUID, content_hash: str
    ) -> SourceRevision | None:
        result = await self._session.execute(
            select(SourceRevisionModel).where(
                SourceRevisionModel.source_id == source_id,
                SourceRevisionModel.content_hash == content_hash,
                SourceRevisionModel.status == RevisionStatus.ACTIVE.value,
            )
        )
        row = result.scalar_one_or_none()
        return _map_revision(row) if row else None

    async def save(self, revision: SourceRevision) -> None:
        row = await self._session.get(SourceRevisionModel, revision.id)
        if row is None:
            self._session.add(
                SourceRevisionModel(
                    id=revision.id,
                    source_id=revision.source_id,
                    workspace_id=revision.workspace_id,
                    status=revision.status.value,
                    content_hash=revision.content_hash,
                    snapshot_object_key=revision.snapshot_object_key,
                    api_version=revision.api_version,
                    api_title=revision.api_title,
                    expected_chunk_count=revision.expected_chunk_count,
                    actual_chunk_count=revision.actual_chunk_count,
                    created_at=revision.created_at,
                    activated_at=revision.activated_at,
                    failed_at=revision.failed_at,
                    failure_reason=revision.failure_reason,
                )
            )
        else:
            row.status = revision.status.value
            row.content_hash = revision.content_hash
            row.snapshot_object_key = revision.snapshot_object_key
            row.api_version = revision.api_version
            row.api_title = revision.api_title
            row.expected_chunk_count = revision.expected_chunk_count
            row.actual_chunk_count = revision.actual_chunk_count
            row.activated_at = revision.activated_at
            row.failed_at = revision.failed_at
            row.failure_reason = revision.failure_reason

    async def activate(self, revision_id: UUID) -> None:
        """Atomically set revision ACTIVE and supersede all others for the same source.

        Runs two UPDATEs in sequence within the caller's transaction.
        """
        # Find the source_id first
        row = await self._session.get(SourceRevisionModel, revision_id)
        if row is None:
            raise ValueError(f"Revision {revision_id} not found")

        source_id = row.source_id
        now = datetime.now(UTC)

        # Supersede any currently active revision
        await self._session.execute(
            update(SourceRevisionModel)
            .where(
                SourceRevisionModel.source_id == source_id,
                SourceRevisionModel.status == RevisionStatus.ACTIVE.value,
            )
            .values(status=RevisionStatus.SUPERSEDED.value)
        )

        # Activate the new one
        await self._session.execute(
            update(SourceRevisionModel)
            .where(SourceRevisionModel.id == revision_id)
            .values(
                status=RevisionStatus.ACTIVE.value,
                activated_at=now,
            )
        )

        logger.info(
            "revision_activated",
            extra={"revision_id": str(revision_id), "source_id": str(source_id)},
        )


# ── JobRepository ─────────────────────────────────────────────────────────────


class PgJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: UUID) -> IngestionJob | None:
        row = await self._session.get(IngestionJobModel, job_id)
        return _map_job(row) if row else None

    async def get_by_revision(self, revision_id: UUID) -> IngestionJob | None:
        result = await self._session.execute(
            select(IngestionJobModel)
            .where(IngestionJobModel.revision_id == revision_id)
            .order_by(IngestionJobModel.created_at.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        return _map_job(row) if row else None

    async def save(self, job: IngestionJob) -> None:
        row = await self._session.get(IngestionJobModel, job.id)
        if row is None:
            self._session.add(
                IngestionJobModel(
                    id=job.id,
                    source_id=job.source_id,
                    revision_id=job.revision_id,
                    workspace_id=job.workspace_id,
                    stage=job.stage.value,
                    attempt=job.attempt,
                    max_attempts=job.max_attempts,
                    error_message=job.error_message,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    started_at=job.started_at,
                    completed_at=job.completed_at,
                )
            )
        else:
            row.stage = job.stage.value
            row.attempt = job.attempt
            row.error_message = job.error_message
            row.updated_at = job.updated_at
            row.started_at = job.started_at
            row.completed_at = job.completed_at


# ── OperationRepository ───────────────────────────────────────────────────────


class PgOperationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, operation_id: UUID) -> ApiOperation | None:
        result = await self._session.execute(
            select(ApiOperationModel).where(ApiOperationModel.id == operation_id)
        )
        row = result.scalar_one_or_none()
        return _map_operation(row) if row else None

    async def list_by_revision(self, revision_id: UUID) -> list[ApiOperation]:
        result = await self._session.execute(
            select(ApiOperationModel).where(
                ApiOperationModel.revision_id == revision_id
            )
        )
        return [_map_operation(r) for r in result.scalars().all()]

    async def find_by_method_path(
        self, revision_id: UUID, method: str, path_normalized: str
    ) -> ApiOperation | None:
        result = await self._session.execute(
            select(ApiOperationModel).where(
                ApiOperationModel.revision_id == revision_id,
                ApiOperationModel.method == method.upper(),
                ApiOperationModel.path_normalized == path_normalized,
            )
        )
        row = result.scalar_one_or_none()
        return _map_operation(row) if row else None

    async def find_by_operation_id(
        self, revision_id: UUID, operation_id: str
    ) -> ApiOperation | None:
        result = await self._session.execute(
            select(ApiOperationModel).where(
                ApiOperationModel.revision_id == revision_id,
                ApiOperationModel.operation_id == operation_id,
            )
        )
        row = result.scalar_one_or_none()
        return _map_operation(row) if row else None

    async def save_many(self, operations: list[ApiOperation]) -> None:
        """Bulk insert operations and their children with ON CONFLICT DO NOTHING."""
        for op in operations:
            stmt = (
                pg_insert(ApiOperationModel)
                .values(
                    id=op.id,
                    revision_id=op.revision_id,
                    workspace_id=op.workspace_id,
                    method=op.method.value,
                    path=op.path,
                    path_normalized=op.path_normalized,
                    operation_id=op.operation_id,
                    summary=op.summary,
                    description=op.description,
                    tags=op.tags,
                    deprecated=op.deprecated,
                    logical_key=op.logical_key,
                    source_pointer=op.source_pointer,
                    security_requirements=op.security_requirements,
                )
                .on_conflict_do_nothing(constraint="uq_operations_revision_logical_key")
            )
            await self._session.execute(stmt)

            # Insert parameters
            for param in op.parameters:
                p_stmt = (
                    pg_insert(ApiParameterModel)
                    .values(
                        id=param.id,
                        revision_id=param.revision_id,
                        operation_id=param.operation_id,
                        name=param.name,
                        location=param.location.value,
                        required=param.required,
                        deprecated=param.deprecated,
                        description=param.description,
                        schema_json=param.schema_json,
                        example_json=param.example_json,
                        source_pointer=param.source_pointer,
                    )
                    .on_conflict_do_nothing()
                )
                await self._session.execute(p_stmt)

            # Insert request body
            if op.request_body:
                rb_stmt = (
                    pg_insert(ApiRequestBodyModel)
                    .values(
                        id=op.request_body.id,
                        operation_id=op.request_body.operation_id,
                        required=op.request_body.required,
                        description=op.request_body.description,
                        content_schemas=op.request_body.content_schemas,
                    )
                    .on_conflict_do_nothing()
                )
                await self._session.execute(rb_stmt)

            # Insert responses
            for resp in op.responses:
                r_stmt = (
                    pg_insert(ApiResponseModel)
                    .values(
                        id=resp.id,
                        operation_id=resp.operation_id,
                        status_code=resp.status_code,
                        description=resp.description,
                        content_schemas=resp.content_schemas,
                        headers=resp.headers,
                    )
                    .on_conflict_do_nothing()
                )
                await self._session.execute(r_stmt)


def _map_operation(row: ApiOperationModel) -> ApiOperation:
    return ApiOperation(
        id=row.id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        method=HttpMethod(row.method),
        path=row.path,
        path_normalized=row.path_normalized,
        operation_id=row.operation_id,
        summary=row.summary,
        description=row.description,
        tags=list(row.tags or []),
        deprecated=row.deprecated,
        logical_key=row.logical_key,
        source_pointer=row.source_pointer,
        security_requirements=list(row.security_requirements or []),
    )


# ── SchemaRepository ──────────────────────────────────────────────────────────


class PgSchemaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, schema_id: UUID) -> ApiSchema | None:
        row = await self._session.get(ApiSchemaModel, schema_id)
        return _map_schema(row) if row else None

    async def list_by_revision(self, revision_id: UUID) -> list[ApiSchema]:
        result = await self._session.execute(
            select(ApiSchemaModel).where(ApiSchemaModel.revision_id == revision_id)
        )
        return [_map_schema(r) for r in result.scalars().all()]

    async def find_by_name(self, revision_id: UUID, name: str) -> ApiSchema | None:
        result = await self._session.execute(
            select(ApiSchemaModel).where(
                ApiSchemaModel.revision_id == revision_id,
                ApiSchemaModel.name == name,
            )
        )
        row = result.scalar_one_or_none()
        return _map_schema(row) if row else None

    async def save_many(self, schemas: list[ApiSchema]) -> None:
        for schema in schemas:
            stmt = (
                pg_insert(ApiSchemaModel)
                .values(
                    id=schema.id,
                    revision_id=schema.revision_id,
                    workspace_id=schema.workspace_id,
                    name=schema.name,
                    description=schema.description,
                    schema_json=schema.schema_json,
                    source_pointer=schema.source_pointer,
                    logical_key=schema.logical_key,
                    nullable=schema.nullable,
                    deprecated=schema.deprecated,
                )
                .on_conflict_do_nothing(constraint="uq_schemas_revision_logical_key")
            )
            await self._session.execute(stmt)


def _map_schema(row: ApiSchemaModel) -> ApiSchema:
    return ApiSchema(
        id=row.id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        name=row.name,
        description=row.description,
        schema_json=row.schema_json,
        source_pointer=row.source_pointer,
        logical_key=row.logical_key,
        nullable=row.nullable,
        deprecated=row.deprecated,
    )


# ── AuthSchemeRepository ──────────────────────────────────────────────────────


class PgAuthSchemeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_revision(self, revision_id: UUID) -> list[AuthScheme]:
        result = await self._session.execute(
            select(AuthSchemeModel).where(AuthSchemeModel.revision_id == revision_id)
        )
        return [_map_auth(r) for r in result.scalars().all()]

    async def save_many(self, schemes: list[AuthScheme]) -> None:
        for scheme in schemes:
            stmt = (
                pg_insert(AuthSchemeModel)
                .values(
                    id=scheme.id,
                    revision_id=scheme.revision_id,
                    workspace_id=scheme.workspace_id,
                    name=scheme.name,
                    scheme_type=scheme.scheme_type.value,
                    description=scheme.description,
                    details_json=scheme.details_json,
                )
                .on_conflict_do_nothing(constraint="uq_auth_schemes_revision_name")
            )
            await self._session.execute(stmt)


def _map_auth(row: AuthSchemeModel) -> AuthScheme:
    return AuthScheme(
        id=row.id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        name=row.name,
        scheme_type=AuthSchemeType(row.scheme_type),
        description=row.description,
        details_json=row.details_json,
    )


# ── ServerRepository (used internally by ingestion) ───────────────────────────


class PgServerRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_revision(self, revision_id: UUID) -> list[ApiServer]:
        result = await self._session.execute(
            select(ApiServerModel).where(ApiServerModel.revision_id == revision_id)
        )
        return [_map_server(r) for r in result.scalars().all()]

    async def save_many(self, servers: list[ApiServer]) -> None:
        for server in servers:
            stmt = (
                pg_insert(ApiServerModel)
                .values(
                    id=server.id,
                    revision_id=server.revision_id,
                    url=server.url,
                    description=server.description,
                    variables=server.variables,
                )
                .on_conflict_do_nothing()
            )
            await self._session.execute(stmt)


def _map_server(row: ApiServerModel) -> ApiServer:
    return ApiServer(
        id=row.id,
        revision_id=row.revision_id,
        url=row.url,
        description=row.description,
        variables=dict(row.variables or {}),
    )


# ── ExampleRepository (used internally by ingestion) ──────────────────────────


class PgExampleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_operation(
        self, revision_id: UUID, operation_id: UUID
    ) -> list[ApiExample]:
        result = await self._session.execute(
            select(ApiExampleModel).where(
                ApiExampleModel.revision_id == revision_id,
                ApiExampleModel.operation_id == operation_id,
            )
        )
        return [_map_example(r) for r in result.scalars().all()]

    async def save_many(self, examples: list[ApiExample]) -> None:
        for ex in examples:
            stmt = (
                pg_insert(ApiExampleModel)
                .values(
                    id=ex.id,
                    revision_id=ex.revision_id,
                    workspace_id=ex.workspace_id,
                    operation_id=ex.operation_id,
                    title=ex.title,
                    description=ex.description,
                    language=ex.language,
                    content=ex.content,
                    source_pointer=ex.source_pointer,
                )
                .on_conflict_do_nothing()
            )
            await self._session.execute(stmt)


def _map_example(row: ApiExampleModel) -> ApiExample:
    return ApiExample(
        id=row.id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        operation_id=row.operation_id,
        title=row.title,
        description=row.description,
        language=row.language,
        content=row.content,
        source_pointer=row.source_pointer,
    )


# ── ErrorDefinitionRepository (used internally by ingestion) ──────────────────


class PgErrorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_operation(
        self, revision_id: UUID, operation_id: UUID
    ) -> list[ErrorDefinition]:
        result = await self._session.execute(
            select(ErrorDefinitionModel).where(
                ErrorDefinitionModel.revision_id == revision_id,
                ErrorDefinitionModel.operation_id == operation_id,
            )
        )
        return [_map_error(r) for r in result.scalars().all()]

    async def find_by_status_code(
        self, revision_id: UUID, status_code: str
    ) -> list[ErrorDefinition]:
        result = await self._session.execute(
            select(ErrorDefinitionModel).where(
                ErrorDefinitionModel.revision_id == revision_id,
                ErrorDefinitionModel.status_code == status_code,
            )
        )
        return [_map_error(r) for r in result.scalars().all()]

    async def save_many(self, errors: list[ErrorDefinition]) -> None:
        for err in errors:
            stmt = (
                pg_insert(ErrorDefinitionModel)
                .values(
                    id=err.id,
                    revision_id=err.revision_id,
                    workspace_id=err.workspace_id,
                    operation_id=err.operation_id,
                    status_code=err.status_code,
                    error_code=err.error_code,
                    title=err.title,
                    description=err.description,
                    source_pointer=err.source_pointer,
                )
                .on_conflict_do_nothing()
            )
            await self._session.execute(stmt)


def _map_error(row: ErrorDefinitionModel) -> ErrorDefinition:
    return ErrorDefinition(
        id=row.id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        operation_id=row.operation_id,
        status_code=row.status_code,
        error_code=row.error_code,
        title=row.title,
        description=row.description,
        source_pointer=row.source_pointer,
    )


# ── EmbeddingProfileRepository ────────────────────────────────────────────────


@dataclass
class EmbeddingProfileRecord:
    """Flat record returned from the DB — avoids crossing ORM objects into app layer."""

    id: UUID
    version: str
    dense_model_id: str
    dense_dimension: int
    sparse_model_id: str
    collection_name: str
    distance_metric: str
    created_at: datetime


def _map_embedding_profile(row: EmbeddingProfileModel) -> EmbeddingProfileRecord:
    return EmbeddingProfileRecord(
        id=row.id,
        version=row.version,
        dense_model_id=row.dense_model_id,
        dense_dimension=row.dense_dimension,
        sparse_model_id=row.sparse_model_id,
        collection_name=row.collection_name,
        distance_metric=row.distance_metric,
        created_at=row.created_at,
    )


class PgEmbeddingProfileRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_version(self, version: str) -> EmbeddingProfileRecord | None:
        result = await self._session.execute(
            select(EmbeddingProfileModel).where(
                EmbeddingProfileModel.version == version
            )
        )
        row = result.scalar_one_or_none()
        return _map_embedding_profile(row) if row else None

    async def save(self, record: EmbeddingProfileRecord) -> None:
        """Insert if not present; skip if version already exists (immutable)."""
        stmt = (
            pg_insert(EmbeddingProfileModel)
            .values(
                id=record.id,
                version=record.version,
                dense_model_id=record.dense_model_id,
                dense_dimension=record.dense_dimension,
                sparse_model_id=record.sparse_model_id,
                collection_name=record.collection_name,
                distance_metric=record.distance_metric,
                created_at=record.created_at,
            )
            .on_conflict_do_nothing(constraint="uq_embedding_profiles_version")
        )
        await self._session.execute(stmt)


# ── ChunkRepository ───────────────────────────────────────────────────────────


class PgChunkRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_many(self, chunks: list[Chunk]) -> None:
        """Bulk insert chunks. On conflict on (revision_id, content_hash), skip."""
        for chunk in chunks:
            stmt = (
                pg_insert(ChunkModel)
                .values(
                    id=chunk.id,
                    revision_id=chunk.revision_id,
                    workspace_id=chunk.workspace_id,
                    source_id=chunk.source_id,
                    embedding_profile_id=chunk.embedding_profile_version,  # stored as profile UUID
                    chunk_type=chunk.chunk_type.value,
                    entity_type=chunk.entity_type,
                    entity_id=chunk.entity_id,
                    title=chunk.title,
                    text=chunk.text,
                    content_hash=chunk.content_hash,
                    qdrant_point_id=chunk.qdrant_point_id,
                    method=chunk.method,
                    path=chunk.path,
                    operation_id_str=chunk.operation_id,
                    tags=chunk.tags,
                    status_codes=chunk.status_codes,
                    api_version=chunk.api_version,
                    source_pointer=chunk.source_pointer,
                    language=chunk.language,
                )
                .on_conflict_do_nothing(constraint="uq_chunks_revision_content_hash")
            )
            await self._session.execute(stmt)

    async def find_chunk_ids_by_entity(
        self, revision_id: UUID, entity_type: str, entity_id: UUID
    ) -> list[UUID]:
        """Return chunk IDs whose entity_type and entity_id match within a revision."""
        result = await self._session.execute(
            select(ChunkModel.id).where(
                ChunkModel.revision_id == revision_id,
                ChunkModel.entity_type == entity_type,
                ChunkModel.entity_id == entity_id,
            )
        )
        return list(result.scalars().all())

    async def find_chunks_by_ids(self, chunk_ids: list[UUID]) -> list[Chunk]:
        """Return chunks whose IDs are in chunk_ids."""
        if not chunk_ids:
            return []
        result = await self._session.execute(
            select(ChunkModel).where(ChunkModel.id.in_(chunk_ids))
        )
        return [_map_chunk(r) for r in result.scalars().all()]

    async def save_many_relations(self, relations: list[ChunkRelation]) -> None:
        """Bulk insert chunk relations. On conflict on (from, to, type), skip."""
        for rel in relations:
            stmt = (
                pg_insert(ChunkRelationModel)
                .values(
                    id=rel.id,
                    revision_id=rel.revision_id,
                    from_chunk_id=rel.from_chunk_id,
                    to_chunk_id=rel.to_chunk_id,
                    relation_type=rel.relation_type.value,
                )
                .on_conflict_do_nothing(constraint="uq_chunk_relations_edge")
            )
            await self._session.execute(stmt)

    async def list_by_revision(self, revision_id: UUID) -> list[Chunk]:
        result = await self._session.execute(
            select(ChunkModel).where(ChunkModel.revision_id == revision_id)
        )
        return [_map_chunk(r) for r in result.scalars().all()]

    async def count_by_revision(self, revision_id: UUID) -> int:
        from sqlalchemy import func

        result = await self._session.execute(
            select(func.count()).where(ChunkModel.revision_id == revision_id)
        )
        return result.scalar_one()


def _map_chunk(row: ChunkModel) -> Chunk:
    return Chunk(
        id=row.id,
        revision_id=row.revision_id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        chunk_type=ChunkType(row.chunk_type),
        entity_type=row.entity_type,
        entity_id=row.entity_id,
        title=row.title,
        text=row.text,
        content_hash=row.content_hash,
        embedding_profile_version=str(row.embedding_profile_id),
        qdrant_point_id=row.qdrant_point_id,
        method=row.method,
        path=row.path,
        operation_id=row.operation_id_str,
        tags=list(row.tags or []),
        status_codes=list(row.status_codes or []),
        api_version=row.api_version,
        source_pointer=row.source_pointer,
        language=row.language,
    )


# ── ChunkRelationRepository ───────────────────────────────────────────────────


class PgChunkRelationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_relations_for_chunks(
        self, chunk_ids: list[UUID], revision_id: UUID
    ) -> list[ChunkRelation]:
        """Return relations whose from_chunk_id is in chunk_ids and revision matches."""
        if not chunk_ids:
            return []
        result = await self._session.execute(
            select(ChunkRelationModel).where(
                ChunkRelationModel.from_chunk_id.in_(chunk_ids),
                ChunkRelationModel.revision_id == revision_id,
            )
        )
        return [_map_chunk_relation(r) for r in result.scalars().all()]

    async def save_many(self, relations: list[ChunkRelation]) -> None:
        """Bulk insert chunk relations. On conflict on (from, to, type), skip."""
        for rel in relations:
            stmt = (
                pg_insert(ChunkRelationModel)
                .values(
                    id=rel.id,
                    revision_id=rel.revision_id,
                    from_chunk_id=rel.from_chunk_id,
                    to_chunk_id=rel.to_chunk_id,
                    relation_type=rel.relation_type.value,
                )
                .on_conflict_do_nothing(constraint="uq_chunk_relations_edge")
            )
            await self._session.execute(stmt)


def _map_chunk_relation(row: ChunkRelationModel) -> ChunkRelation:
    from fetch.domain.enums import ChunkRelationType

    return ChunkRelation(
        id=row.id,
        from_chunk_id=row.from_chunk_id,
        to_chunk_id=row.to_chunk_id,
        relation_type=ChunkRelationType(row.relation_type),
        revision_id=row.revision_id,
    )


# ── QueryRunRepository ────────────────────────────────────────────────────────


def _citations_to_json(citations: list[Citation]) -> list[dict[str, object]]:
    """Serialise Citation value objects to plain dicts for JSONB storage."""
    return [
        {
            "source_id": c.source_id,
            "chunk_id": str(c.chunk_id),
            "entity_type": c.entity_type,
            "entity_id": str(c.entity_id) if c.entity_id else None,
            "title": c.title,
            "content": c.content,
            "source_url": c.source_url,
            "source_pointer": c.source_pointer,
            "api_version": c.api_version,
            "method": c.method,
            "path": c.path,
        }
        for c in citations
    ]


def _citations_from_json(raw: list[dict[str, object]]) -> list[Citation]:
    """Deserialise Citation value objects from JSONB storage."""
    result: list[Citation] = []
    for d in raw:
        entity_id_raw = d.get("entity_id")
        result.append(
            Citation(
                source_id=str(d["source_id"]),
                chunk_id=UUID(str(d["chunk_id"])),
                entity_type=str(d.get("entity_type", "")),
                entity_id=UUID(str(entity_id_raw)) if entity_id_raw else None,
                title=str(d.get("title", "")),
                content=str(d.get("content", "")),
                source_url=str(d["source_url"]) if d.get("source_url") else None,
                source_pointer=(
                    str(d["source_pointer"]) if d.get("source_pointer") else None
                ),
                api_version=str(d["api_version"]) if d.get("api_version") else None,
                method=str(d["method"]) if d.get("method") else None,
                path=str(d["path"]) if d.get("path") else None,
            )
        )
    return result


def _map_query_run(row: QueryRunModel) -> QueryRun:
    return QueryRun(
        id=row.id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        revision_id=row.revision_id,
        workflow=QueryWorkflow(row.workflow),
        question=row.question,
        answer=row.answer,
        citations=_citations_from_json(
            cast(list[dict[str, object]], row.citations or [])
        ),
        support_status=SupportStatus(row.support_status),
        warnings=cast(list[str], list(row.warnings or [])),
        retrieval_ms=row.retrieval_ms,
        generation_ms=row.generation_ms,
        total_ms=row.total_ms,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        dense_candidate_count=row.dense_candidate_count,
        bm25_candidate_count=row.bm25_candidate_count,
        fused_candidate_count=row.fused_candidate_count,
        reranked_candidate_count=row.reranked_candidate_count,
        expanded_candidate_count=row.expanded_candidate_count,
        exact_match_found=row.exact_match_found,
        created_at=row.created_at,
        intent_classification=row.intent_classification,
        prompt_version=row.prompt_version,
    )


class PgQueryRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: QueryRun) -> None:
        """Insert or update a query run.

        Uses INSERT … ON CONFLICT (id) DO UPDATE so that a row written during
        retrieval can be updated after generation without a separate fetch.
        """
        stmt = (
            pg_insert(QueryRunModel)
            .values(
                id=run.id,
                workspace_id=run.workspace_id,
                source_id=run.source_id,
                revision_id=run.revision_id,
                workflow=run.workflow.value,
                question=run.question,
                answer=run.answer,
                citations=_citations_to_json(run.citations),
                support_status=run.support_status.value,
                warnings=list(run.warnings),
                retrieval_ms=run.retrieval_ms,
                generation_ms=run.generation_ms,
                total_ms=run.total_ms,
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                dense_candidate_count=run.dense_candidate_count,
                bm25_candidate_count=run.bm25_candidate_count,
                fused_candidate_count=run.fused_candidate_count,
                reranked_candidate_count=run.reranked_candidate_count,
                expanded_candidate_count=run.expanded_candidate_count,
                exact_match_found=run.exact_match_found,
                created_at=run.created_at,
                intent_classification=run.intent_classification,
                prompt_version=run.prompt_version,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "answer": run.answer,
                    "citations": _citations_to_json(run.citations),
                    "support_status": run.support_status.value,
                    "warnings": list(run.warnings),
                    "retrieval_ms": run.retrieval_ms,
                    "generation_ms": run.generation_ms,
                    "total_ms": run.total_ms,
                    "prompt_tokens": run.prompt_tokens,
                    "completion_tokens": run.completion_tokens,
                    "dense_candidate_count": run.dense_candidate_count,
                    "bm25_candidate_count": run.bm25_candidate_count,
                    "fused_candidate_count": run.fused_candidate_count,
                    "reranked_candidate_count": run.reranked_candidate_count,
                    "expanded_candidate_count": run.expanded_candidate_count,
                    "exact_match_found": run.exact_match_found,
                    "intent_classification": run.intent_classification,
                    "prompt_version": run.prompt_version,
                },
            )
        )
        await self._session.execute(stmt)
        logger.debug(
            "query_run_saved",
            extra={"run_id": str(run.id), "retrieval_ms": run.retrieval_ms},
        )

    async def get(self, run_id: UUID) -> QueryRun | None:
        row = await self._session.get(QueryRunModel, run_id)
        return _map_query_run(row) if row else None

    async def list_by_source(self, source_id: UUID, limit: int = 50) -> list[QueryRun]:
        result = await self._session.execute(
            select(QueryRunModel)
            .where(QueryRunModel.source_id == source_id)
            .order_by(QueryRunModel.created_at.desc())
            .limit(limit)
        )
        return [_map_query_run(r) for r in result.scalars().all()]


# ── PgParameterRepository ─────────────────────────────────────────────────────


def _map_parameter(row: ApiParameterModel) -> ApiParameter:
    return ApiParameter(
        id=row.id,
        revision_id=row.revision_id,
        operation_id=row.operation_id,
        name=row.name,
        location=ParameterLocation(row.location),
        required=row.required,
        deprecated=row.deprecated,
        description=row.description,
        schema_json=row.schema_json,
        example_json=row.example_json,
        source_pointer=row.source_pointer,
    )


class PgParameterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_operation(self, operation_id: UUID) -> list[ApiParameter]:
        result = await self._session.execute(
            select(ApiParameterModel).where(
                ApiParameterModel.operation_id == operation_id
            )
        )
        return [_map_parameter(r) for r in result.scalars().all()]


# ── PgRequestBodyRepository ───────────────────────────────────────────────────


def _map_request_body(row: ApiRequestBodyModel) -> ApiRequestBody:
    return ApiRequestBody(
        id=row.id,
        operation_id=row.operation_id,
        required=row.required,
        description=row.description,
        content_schemas=dict(row.content_schemas or {}),
    )


class PgRequestBodyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_operation(self, operation_id: UUID) -> ApiRequestBody | None:
        result = await self._session.execute(
            select(ApiRequestBodyModel).where(
                ApiRequestBodyModel.operation_id == operation_id
            )
        )
        row = result.scalar_one_or_none()
        return _map_request_body(row) if row else None


# ── PgResponseRepository ──────────────────────────────────────────────────────


def _map_response(row: ApiResponseModel) -> ApiResponse:
    return ApiResponse(
        id=row.id,
        operation_id=row.operation_id,
        status_code=row.status_code,
        description=row.description,
        content_schemas=dict(row.content_schemas or {}),
        headers=dict(row.headers or {}),
    )


class PgResponseRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_operation(self, operation_id: UUID) -> list[ApiResponse]:
        result = await self._session.execute(
            select(ApiResponseModel).where(
                ApiResponseModel.operation_id == operation_id
            )
        )
        return [_map_response(r) for r in result.scalars().all()]


# ── IntegrationRunRepository ──────────────────────────────────────────────────


def _validation_report_to_json(report: ValidationReport) -> dict[str, object]:
    return {
        "contract_valid": report.contract_valid,
        "syntax_valid": report.syntax_valid,
        "overall_valid": report.overall_valid,
        "issues": [
            {
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "field": i.field,
            }
            for i in report.issues
        ],
    }


def _validation_report_from_json(d: dict[str, object]) -> ValidationReport:
    raw_issues = d.get("issues", [])
    issues = [
        ValidationIssue(
            severity=str(i["severity"]),
            category=str(i["category"]),
            message=str(i["message"]),
            field=str(i["field"]) if i.get("field") else None,
        )
        for i in cast(list[dict[str, object]], raw_issues)
    ]
    return ValidationReport(
        contract_valid=bool(d["contract_valid"]),
        syntax_valid=bool(d["syntax_valid"]),
        overall_valid=bool(d["overall_valid"]),
        issues=issues,
    )


def _map_integration_run(row: IntegrationRunModel) -> IntegrationRun:
    validation_report: ValidationReport | None = None
    if row.validation_report is not None:
        validation_report = _validation_report_from_json(row.validation_report)
    if row.operation_id is None:
        raise ValueError(f"IntegrationRun {row.id} has null operation_id")
    return IntegrationRun(
        id=row.id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        revision_id=row.revision_id,
        operation_id=row.operation_id,
        language=GenerationLanguage(row.language),
        generated_code=row.generated_code,
        validation_report=validation_report,
        support_status=SupportStatus(row.support_status),
        warnings=cast(list[str], list(row.warnings or [])),
        prompt_version=row.prompt_version,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        context_assembly_ms=row.context_assembly_ms,
        generation_ms=row.generation_ms,
        validation_ms=row.validation_ms,
        total_ms=row.total_ms,
        created_at=row.created_at,
    )


class PgIntegrationRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: IntegrationRun) -> None:
        validation_json = (
            _validation_report_to_json(run.validation_report)
            if run.validation_report is not None
            else None
        )
        stmt = (
            pg_insert(IntegrationRunModel)
            .values(
                id=run.id,
                workspace_id=run.workspace_id,
                source_id=run.source_id,
                revision_id=run.revision_id,
                operation_id=run.operation_id,
                language=run.language.value,
                generated_code=run.generated_code,
                validation_report=validation_json,
                support_status=run.support_status.value,
                warnings=list(run.warnings),
                prompt_version=run.prompt_version,
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                context_assembly_ms=run.context_assembly_ms,
                generation_ms=run.generation_ms,
                validation_ms=run.validation_ms,
                total_ms=run.total_ms,
                created_at=run.created_at,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "generated_code": run.generated_code,
                    "validation_report": validation_json,
                    "support_status": run.support_status.value,
                    "warnings": list(run.warnings),
                    "prompt_tokens": run.prompt_tokens,
                    "completion_tokens": run.completion_tokens,
                    "context_assembly_ms": run.context_assembly_ms,
                    "generation_ms": run.generation_ms,
                    "validation_ms": run.validation_ms,
                    "total_ms": run.total_ms,
                },
            )
        )
        await self._session.execute(stmt)
        logger.debug("integration_run_saved", extra={"run_id": str(run.id)})

    async def get(self, run_id: UUID) -> IntegrationRun | None:
        row = await self._session.get(IntegrationRunModel, run_id)
        return _map_integration_run(row) if row else None

    async def list_by_source(
        self, source_id: UUID, limit: int = 50
    ) -> list[IntegrationRun]:
        result = await self._session.execute(
            select(IntegrationRunModel)
            .where(IntegrationRunModel.source_id == source_id)
            .order_by(IntegrationRunModel.created_at.desc())
            .limit(limit)
        )
        return [_map_integration_run(r) for r in result.scalars().all()]


# ── DiagnosticRunRepository ───────────────────────────────────────────────────


def _diagnostic_to_json(diagnostic: RequestDiagnostic) -> dict[str, object]:
    req = diagnostic.parsed_request
    parsed_dict: dict[str, object] = {
        "method": req.method,
        "url": req.url,
        "headers": dict(req.headers),
        "body_raw": req.body_raw,
        "body_json": req.body_json,
        "content_type": req.content_type,
        "auth_header": None,  # NEVER persist auth header value
        "query_params": dict(req.query_params),
        "is_url_encoded_body": req.is_url_encoded_body,
    }

    endpoint_dict: dict[str, object] | None = None
    if diagnostic.endpoint_match is not None:
        em = diagnostic.endpoint_match
        endpoint_dict = {
            "operation_id": str(em.operation.id) if em.operation else None,
            "path_params": dict(em.path_params),
            "match_confidence": str(em.match_confidence),
        }

    findings_list: list[dict[str, object]] = [
        {
            "severity": f.severity,
            "category": str(f.category),
            "message": f.message,
            "field": f.field,
            "canonical_value": f.canonical_value,
        }
        for f in diagnostic.findings
    ]

    error_status_dict: dict[str, object] | None = None
    if diagnostic.error_status_match is not None:
        esm = diagnostic.error_status_match
        error_status_dict = {
            "status_code": esm.status_code,
            "matched_definitions": [
                {
                    "id": str(d.id),
                    "status_code": d.status_code,
                    "title": d.title,
                    "description": d.description,
                }
                for d in esm.matched_definitions
            ],
            "is_documented": esm.is_documented,
        }

    return {
        "parsed_request": parsed_dict,
        "endpoint_match": endpoint_dict,
        "findings": findings_list,
        "error_status_match": error_status_dict,
        "corrected_curl": diagnostic.corrected_curl,
        "is_valid": diagnostic.is_valid,
    }


def _diagnostic_from_json(d: dict[str, object]) -> RequestDiagnostic:
    req_d = cast(dict[str, object], d["parsed_request"])
    parsed = ParsedRequest(
        method=str(req_d["method"]),
        url=str(req_d["url"]),
        headers=cast(dict[str, str], req_d.get("headers") or {}),
        body_raw=str(req_d["body_raw"]) if req_d.get("body_raw") is not None else None,
        body_json=cast(dict[str, object], req_d.get("body_json")),
        content_type=str(req_d["content_type"]) if req_d.get("content_type") else None,
        auth_header=None,  # never persisted
        query_params=cast(dict[str, str], req_d.get("query_params") or {}),
        is_url_encoded_body=bool(req_d.get("is_url_encoded_body", False)),
    )

    findings = [
        DiagnosticFinding(
            severity=str(f["severity"]),
            category=DiagnosticCategory(str(f["category"])),
            message=str(f["message"]),
            field=str(f["field"]) if f.get("field") else None,
            canonical_value=str(f["canonical_value"])
            if f.get("canonical_value")
            else None,
        )
        for f in cast(list[dict[str, object]], d.get("findings") or [])
    ]

    em_d = d.get("endpoint_match")
    endpoint_match: EndpointMatch | None = None
    if em_d is not None:
        em_dict = cast(dict[str, object], em_d)
        endpoint_match = EndpointMatch(
            operation=None,  # operation not re-hydrated from JSONB
            path_params=cast(dict[str, str], em_dict.get("path_params") or {}),
            match_confidence=MatchConfidence(str(em_dict["match_confidence"])),
        )

    esm_d = d.get("error_status_match")
    error_status_match: ErrorStatusMatch | None = None
    if esm_d is not None:
        esm_dict = cast(dict[str, object], esm_d)
        error_status_match = ErrorStatusMatch(
            status_code=str(esm_dict["status_code"]),
            matched_definitions=[],
            is_documented=bool(esm_dict["is_documented"]),
        )

    return RequestDiagnostic(
        parsed_request=parsed,
        endpoint_match=endpoint_match,
        findings=findings,
        error_status_match=error_status_match,
        corrected_curl=str(d["corrected_curl"]) if d.get("corrected_curl") else None,
        is_valid=bool(d.get("is_valid", False)),
    )


def _map_diagnostic_run(row: RequestDiagnosticRunModel) -> RequestDiagnosticRun:
    diagnostic: RequestDiagnostic | None = None
    if row.diagnostic is not None:
        diagnostic = _diagnostic_from_json(row.diagnostic)
    return RequestDiagnosticRun(
        id=row.id,
        workspace_id=row.workspace_id,
        source_id=row.source_id,
        revision_id=row.revision_id,
        operation_id=row.operation_id,
        input_type=DiagnosticInputType(row.input_type),
        raw_input=row.raw_input,
        parsed_method=row.parsed_method,
        parsed_url=row.parsed_url,
        received_status_code=row.received_status_code,
        diagnostic=diagnostic,
        explanation=row.explanation,
        corrected_curl=row.corrected_curl,
        is_valid=row.is_valid,
        support_status=SupportStatus(row.support_status),
        prompt_version=row.prompt_version,
        prompt_tokens=row.prompt_tokens,
        completion_tokens=row.completion_tokens,
        parse_ms=row.parse_ms,
        match_ms=row.match_ms,
        validate_ms=row.validate_ms,
        explanation_ms=row.explanation_ms,
        total_ms=row.total_ms,
        created_at=row.created_at,
    )


class PgVersionDiffRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_revision_by_source_and_label(
        self, source_id: UUID, version_label: str
    ) -> SourceRevision | None:
        result = await self._session.execute(
            select(SourceRevisionModel).where(
                SourceRevisionModel.source_id == source_id,
                SourceRevisionModel.api_version == version_label,
            )
        )
        row = result.scalar_one_or_none()
        return _map_revision(row) if row else None

    async def list_operations_for_revision(
        self, revision_id: UUID
    ) -> list[ApiOperation]:
        result = await self._session.execute(
            select(ApiOperationModel).where(
                ApiOperationModel.revision_id == revision_id
            )
        )
        return [_map_operation(r) for r in result.scalars().all()]

    async def list_schemas_for_revision(self, revision_id: UUID) -> list[ApiSchema]:
        result = await self._session.execute(
            select(ApiSchemaModel).where(ApiSchemaModel.revision_id == revision_id)
        )
        return [_map_schema(r) for r in result.scalars().all()]

    async def list_auth_for_revision(self, revision_id: UUID) -> list[AuthScheme]:
        result = await self._session.execute(
            select(AuthSchemeModel).where(AuthSchemeModel.revision_id == revision_id)
        )
        return [_map_auth(r) for r in result.scalars().all()]


class PgDiagnosticRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: RequestDiagnosticRun) -> None:
        diagnostic_json = (
            _diagnostic_to_json(run.diagnostic) if run.diagnostic is not None else None
        )
        stmt = (
            pg_insert(RequestDiagnosticRunModel)
            .values(
                id=run.id,
                workspace_id=run.workspace_id,
                source_id=run.source_id,
                revision_id=run.revision_id,
                operation_id=run.operation_id,
                input_type=run.input_type.value,
                raw_input=run.raw_input,
                parsed_method=run.parsed_method,
                parsed_url=run.parsed_url,
                received_status_code=run.received_status_code,
                diagnostic=diagnostic_json,
                explanation=run.explanation,
                corrected_curl=run.corrected_curl,
                is_valid=run.is_valid,
                support_status=run.support_status.value,
                prompt_version=run.prompt_version,
                prompt_tokens=run.prompt_tokens,
                completion_tokens=run.completion_tokens,
                parse_ms=run.parse_ms,
                match_ms=run.match_ms,
                validate_ms=run.validate_ms,
                explanation_ms=run.explanation_ms,
                total_ms=run.total_ms,
                created_at=run.created_at,
            )
            .on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "diagnostic": diagnostic_json,
                    "explanation": run.explanation,
                    "corrected_curl": run.corrected_curl,
                    "is_valid": run.is_valid,
                    "support_status": run.support_status.value,
                    "prompt_tokens": run.prompt_tokens,
                    "completion_tokens": run.completion_tokens,
                    "parse_ms": run.parse_ms,
                    "match_ms": run.match_ms,
                    "validate_ms": run.validate_ms,
                    "explanation_ms": run.explanation_ms,
                    "total_ms": run.total_ms,
                },
            )
        )
        await self._session.execute(stmt)
        logger.debug("diagnostic_run_saved", extra={"run_id": str(run.id)})

    async def get(self, run_id: UUID) -> RequestDiagnosticRun | None:
        row = await self._session.get(RequestDiagnosticRunModel, run_id)
        return _map_diagnostic_run(row) if row else None

    async def list_by_source(
        self, source_id: UUID, limit: int = 50
    ) -> list[RequestDiagnosticRun]:
        result = await self._session.execute(
            select(RequestDiagnosticRunModel)
            .where(RequestDiagnosticRunModel.source_id == source_id)
            .order_by(RequestDiagnosticRunModel.created_at.desc())
            .limit(limit)
        )
        return [_map_diagnostic_run(r) for r in result.scalars().all()]
