"""Concrete async SQLAlchemy repository implementations.

Each class implements a domain protocol from domain/protocols.py.
ORM models are never returned — they are mapped to domain entities here.
All methods receive an AsyncSession injected from the caller.
"""

import json
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

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
    ErrorDefinition,
    IngestionJob,
    SourceRevision,
)
from fetch.domain.enums import (
    AuthSchemeType,
    HttpMethod,
    IngestionStage,
    ParameterLocation,
    RevisionStatus,
    SourceType,
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
    ErrorDefinitionModel,
    IngestionJobModel,
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
            select(ApiOperationModel)
            .where(ApiOperationModel.id == operation_id)
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
                .on_conflict_do_nothing(
                    constraint="uq_operations_revision_logical_key"
                )
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


# ── ExampleRepository (used internally by ingestion) ──────────────────────────


class PgExampleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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


# ── ErrorDefinitionRepository (used internally by ingestion) ──────────────────


class PgErrorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

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
