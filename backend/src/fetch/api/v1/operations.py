"""Operation and auth scheme read endpoints.

GET /v1/sources/{source_id}/operations          — list all operations
GET /v1/operations/{operation_id}               — get one operation
GET /v1/sources/{source_id}/auth                — list auth schemes
GET /v1/sources/{source_id}/schemas             — list schema names
GET /v1/schemas/{schema_id}                     — get one schema
"""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from fetch.api.dependencies import get_workspace_id
from fetch.infrastructure.db.repositories import (
    PgAuthSchemeRepository,
    PgOperationRepository,
    PgRevisionRepository,
    PgSchemaRepository,
    PgSourceRepository,
)
from fetch.infrastructure.db.session import get_session

router = APIRouter(prefix="/v1", tags=["operations"])


# ── Response models ───────────────────────────────────────────────────────────


class OperationSummary(BaseModel):
    operation_id: UUID
    method: str
    path: str
    path_normalized: str
    summary: str | None
    tags: list[str]
    deprecated: bool
    operation_id_str: str | None


class OperationDetail(OperationSummary):
    description: str | None
    security_requirements: list
    source_pointer: str | None


class AuthSchemeResponse(BaseModel):
    auth_scheme_id: UUID
    name: str
    scheme_type: str
    description: str | None
    details_json: str


class SchemaSummary(BaseModel):
    schema_id: UUID
    name: str
    description: str | None
    nullable: bool
    deprecated: bool
    source_pointer: str | None


class SchemaDetail(SchemaSummary):
    schema_json: str


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _resolve_active_revision(source_id: UUID, workspace_id: UUID) -> UUID:
    """Return the active revision ID or raise 404."""
    async with get_session() as session:
        source_repo = PgSourceRepository(session)
        source = await source_repo.get(source_id)
        if source is None or source.workspace_id != workspace_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"code": "SOURCE_NOT_FOUND", "message": "Source not found."},
            )

        rev_repo = PgRevisionRepository(session)
        revision = await rev_repo.get_active(source_id)

    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "NO_ACTIVE_REVISION",
                "message": "Source has no active revision. Ingestion may still be in progress.",
            },
        )
    return revision.id


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "/sources/{source_id}/operations",
    response_model=list[OperationSummary],
    summary="List all operations for the active revision",
)
async def list_operations(source_id: UUID) -> list[OperationSummary]:
    workspace_id = get_workspace_id()
    revision_id = await _resolve_active_revision(source_id, workspace_id)

    async with get_session() as session:
        repo = PgOperationRepository(session)
        operations = await repo.list_by_revision(revision_id)

    return [
        OperationSummary(
            operation_id=op.id,
            method=op.method.value,
            path=op.path,
            path_normalized=op.path_normalized,
            summary=op.summary,
            tags=op.tags,
            deprecated=op.deprecated,
            operation_id_str=op.operation_id,
        )
        for op in operations
    ]


@router.get(
    "/operations/{operation_id}",
    response_model=OperationDetail,
    summary="Get a single operation by ID",
)
async def get_operation(operation_id: UUID) -> OperationDetail:
    workspace_id = get_workspace_id()
    async with get_session() as session:
        repo = PgOperationRepository(session)
        op = await repo.get(operation_id)

    if op is None or op.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "OPERATION_NOT_FOUND", "message": "Operation not found."},
        )

    return OperationDetail(
        operation_id=op.id,
        method=op.method.value,
        path=op.path,
        path_normalized=op.path_normalized,
        summary=op.summary,
        tags=op.tags,
        deprecated=op.deprecated,
        operation_id_str=op.operation_id,
        description=op.description,
        security_requirements=op.security_requirements,
        source_pointer=op.source_pointer,
    )


@router.get(
    "/sources/{source_id}/auth",
    response_model=list[AuthSchemeResponse],
    summary="List auth schemes for the active revision",
)
async def list_auth_schemes(source_id: UUID) -> list[AuthSchemeResponse]:
    workspace_id = get_workspace_id()
    revision_id = await _resolve_active_revision(source_id, workspace_id)

    async with get_session() as session:
        repo = PgAuthSchemeRepository(session)
        schemes = await repo.list_by_revision(revision_id)

    return [
        AuthSchemeResponse(
            auth_scheme_id=s.id,
            name=s.name,
            scheme_type=s.scheme_type.value,
            description=s.description,
            details_json=s.details_json,
        )
        for s in schemes
    ]


@router.get(
    "/sources/{source_id}/schemas",
    response_model=list[SchemaSummary],
    summary="List schema names for the active revision",
)
async def list_schemas(source_id: UUID) -> list[SchemaSummary]:
    workspace_id = get_workspace_id()
    revision_id = await _resolve_active_revision(source_id, workspace_id)

    async with get_session() as session:
        repo = PgSchemaRepository(session)
        schemas = await repo.list_by_revision(revision_id)

    return [
        SchemaSummary(
            schema_id=s.id,
            name=s.name,
            description=s.description,
            nullable=s.nullable,
            deprecated=s.deprecated,
            source_pointer=s.source_pointer,
        )
        for s in schemas
    ]


@router.get(
    "/schemas/{schema_id}",
    response_model=SchemaDetail,
    summary="Get a single schema with its JSON Schema body",
)
async def get_schema(schema_id: UUID) -> SchemaDetail:
    workspace_id = get_workspace_id()
    async with get_session() as session:
        repo = PgSchemaRepository(session)
        schema = await repo.get(schema_id)

    if schema is None or schema.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "SCHEMA_NOT_FOUND", "message": "Schema not found."},
        )

    return SchemaDetail(
        schema_id=schema.id,
        name=schema.name,
        description=schema.description,
        nullable=schema.nullable,
        deprecated=schema.deprecated,
        source_pointer=schema.source_pointer,
        schema_json=schema.schema_json,
    )
