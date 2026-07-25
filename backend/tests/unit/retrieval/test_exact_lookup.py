"""Unit tests for ExactLookup.

All repositories are mocked with AsyncMock — no database required.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from fetch.application.retrieval.exact_lookup import (
    ExactLookup,
    ExactLookupResult,
    _normalize_path,
)
from fetch.application.retrieval.normalizer import NormalizedQuery
from fetch.domain.entities import ApiOperation, ApiSchema
from fetch.domain.enums import HttpMethod

# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_operation(
    revision_id: UUID,
    operation_id: str | None = "getUsers",
    method: HttpMethod = HttpMethod.GET,
    path: str = "/v1/users",
) -> ApiOperation:
    return ApiOperation(
        id=uuid4(),
        revision_id=revision_id,
        workspace_id=uuid4(),
        method=method,
        path=path,
        path_normalized=path.lower(),
        operation_id=operation_id,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key=f"src:v1:{method.value}:{path.lower()}",
        source_pointer=None,
        security_requirements=[],
    )


def _make_schema(revision_id: UUID, name: str = "UserSchema") -> ApiSchema:
    return ApiSchema(
        id=uuid4(),
        revision_id=revision_id,
        workspace_id=uuid4(),
        name=name,
        description=None,
        schema_json="{}",
        source_pointer=None,
        logical_key=f"src:v1:{name}",
        nullable=False,
        deprecated=False,
    )


@pytest.fixture
def revision_id() -> UUID:
    return uuid4()


@pytest.fixture
def workspace_id() -> UUID:
    return uuid4()


@pytest.fixture
def chunk_ids() -> list[UUID]:
    return [uuid4(), uuid4()]


def _make_repos(
    operation: ApiOperation | None = None,
    schema: ApiSchema | None = None,
    chunk_ids: list[UUID] | None = None,
) -> tuple[AsyncMock, AsyncMock, AsyncMock]:
    operation_repo = AsyncMock()
    operation_repo.find_by_method_path = AsyncMock(return_value=operation)
    operation_repo.find_by_operation_id = AsyncMock(return_value=operation)

    schema_repo = AsyncMock()
    schema_repo.find_by_name = AsyncMock(return_value=schema)

    chunk_repo = AsyncMock()
    chunk_repo.find_chunk_ids_by_entity = AsyncMock(return_value=chunk_ids or [])

    return operation_repo, schema_repo, chunk_repo


# ── Path normalisation helper ─────────────────────────────────────────────────


def test_normalize_path_strips_trailing_slash() -> None:
    assert _normalize_path("/v1/users/") == "/v1/users"


def test_normalize_path_lowercases_static_segments() -> None:
    assert _normalize_path("/V1/Users") == "/v1/users"


def test_normalize_path_preserves_param_placeholders() -> None:
    assert _normalize_path("/v1/Users/{userId}/Orders") == "/v1/users/{userId}/orders"


def test_normalize_path_root_slash() -> None:
    assert _normalize_path("/") == "/"


# ── Method + path match ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_method_path_match_calls_find_by_method_path(
    revision_id: UUID, workspace_id: UUID, chunk_ids: list[UUID]
) -> None:
    operation = _make_operation(revision_id)
    operation_repo, schema_repo, chunk_repo = _make_repos(
        operation=operation, chunk_ids=chunk_ids
    )
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="GET /v1/users",
        method="GET",
        path_pattern="/v1/users",
    )
    result = await lookup.lookup(query, revision_id, workspace_id)

    operation_repo.find_by_method_path.assert_awaited_once_with(
        revision_id, "GET", "/v1/users"
    )
    assert result.matched_entity_type == "operation"
    assert result.matched_entity_id == operation.id
    assert result.chunk_ids == chunk_ids


@pytest.mark.asyncio
async def test_method_path_match_resolves_chunk_ids(
    revision_id: UUID, workspace_id: UUID, chunk_ids: list[UUID]
) -> None:
    operation = _make_operation(revision_id)
    operation_repo, schema_repo, chunk_repo = _make_repos(
        operation=operation, chunk_ids=chunk_ids
    )
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="GET /v1/users",
        method="GET",
        path_pattern="/v1/users",
    )
    result = await lookup.lookup(query, revision_id, workspace_id)

    chunk_repo.find_chunk_ids_by_entity.assert_awaited_once_with(
        revision_id, "operation", operation.id
    )
    assert result.chunk_ids == chunk_ids


@pytest.mark.asyncio
async def test_method_path_match_normalizes_path_before_lookup(
    revision_id: UUID, workspace_id: UUID
) -> None:
    operation_repo, schema_repo, chunk_repo = _make_repos(operation=None)
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="GET /V1/Users/",
        method="GET",
        path_pattern="/V1/Users/",
    )
    await lookup.lookup(query, revision_id, workspace_id)

    operation_repo.find_by_method_path.assert_awaited_once_with(
        revision_id, "GET", "/v1/users"
    )


@pytest.mark.asyncio
async def test_method_without_path_skips_method_path_lookup(
    revision_id: UUID, workspace_id: UUID
) -> None:
    """If only method is set (no path_pattern), find_by_method_path is NOT called."""
    operation_repo, schema_repo, chunk_repo = _make_repos()
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(raw_text="What does GET return?", method="GET")
    await lookup.lookup(query, revision_id, workspace_id)

    operation_repo.find_by_method_path.assert_not_awaited()


# ── operation_id match ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_operation_id_match_calls_find_by_operation_id(
    revision_id: UUID, workspace_id: UUID, chunk_ids: list[UUID]
) -> None:
    operation = _make_operation(revision_id, operation_id="getUsers")
    operation_repo, schema_repo, chunk_repo = _make_repos(
        operation=operation, chunk_ids=chunk_ids
    )
    # No method+path so method_path branch is skipped; operation_id branch fires.
    operation_repo.find_by_method_path = AsyncMock(return_value=None)
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="how does getUsers work",
        operation_id="getUsers",
    )
    result = await lookup.lookup(query, revision_id, workspace_id)

    operation_repo.find_by_operation_id.assert_awaited_once_with(
        revision_id, "getUsers"
    )
    assert result.matched_entity_type == "operation"
    assert result.matched_entity_id == operation.id
    assert result.chunk_ids == chunk_ids


@pytest.mark.asyncio
async def test_operation_id_not_called_when_method_path_matched(
    revision_id: UUID, workspace_id: UUID
) -> None:
    """If method+path already matched, operation_id lookup is not attempted."""
    operation = _make_operation(revision_id)
    operation_repo, schema_repo, chunk_repo = _make_repos(operation=operation)
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="GET /v1/users getUsers",
        method="GET",
        path_pattern="/v1/users",
        operation_id="getUsers",
    )
    await lookup.lookup(query, revision_id, workspace_id)

    operation_repo.find_by_operation_id.assert_not_awaited()


# ── Schema name match ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_schema_name_match_calls_find_by_name(
    revision_id: UUID, workspace_id: UUID, chunk_ids: list[UUID]
) -> None:
    schema = _make_schema(revision_id, name="UserSchema")
    operation_repo, schema_repo, chunk_repo = _make_repos(
        schema=schema, chunk_ids=chunk_ids
    )
    operation_repo.find_by_method_path = AsyncMock(return_value=None)
    operation_repo.find_by_operation_id = AsyncMock(return_value=None)
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="tell me about UserSchema",
        schema_names=["UserSchema"],
    )
    result = await lookup.lookup(query, revision_id, workspace_id)

    schema_repo.find_by_name.assert_awaited_once_with(revision_id, "UserSchema")
    assert result.matched_entity_type == "schema"
    assert result.matched_entity_id == schema.id
    assert result.chunk_ids == chunk_ids


@pytest.mark.asyncio
async def test_schema_name_returns_first_match(
    revision_id: UUID, workspace_id: UUID
) -> None:
    """When multiple schema names are in the query, the first match wins."""
    schema_a = _make_schema(revision_id, name="OrderSchema")
    operation_repo, schema_repo, chunk_repo = _make_repos(schema=schema_a)
    operation_repo.find_by_method_path = AsyncMock(return_value=None)
    operation_repo.find_by_operation_id = AsyncMock(return_value=None)
    # First schema name misses, second hits.
    schema_repo.find_by_name = AsyncMock(side_effect=[None, schema_a])
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="UserSchema and OrderSchema",
        schema_names=["UserSchema", "OrderSchema"],
    )
    result = await lookup.lookup(query, revision_id, workspace_id)

    assert result.matched_entity_type == "schema"
    assert result.matched_entity_id == schema_a.id
    # find_by_name called twice — once for each name
    assert schema_repo.find_by_name.await_count == 2


# ── No match ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_match_returns_empty_result(
    revision_id: UUID, workspace_id: UUID
) -> None:
    operation_repo, schema_repo, chunk_repo = _make_repos(
        operation=None, schema=None, chunk_ids=[]
    )
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(raw_text="What is authentication?")
    result = await lookup.lookup(query, revision_id, workspace_id)

    assert result == ExactLookupResult()
    assert result.chunk_ids == []
    assert result.matched_entity_type is None
    assert result.matched_entity_id is None
    chunk_repo.find_chunk_ids_by_entity.assert_not_awaited()


@pytest.mark.asyncio
async def test_empty_chunk_ids_when_entity_has_no_chunks(
    revision_id: UUID, workspace_id: UUID
) -> None:
    operation = _make_operation(revision_id)
    operation_repo, schema_repo, chunk_repo = _make_repos(
        operation=operation, chunk_ids=[]
    )
    lookup = ExactLookup(operation_repo, schema_repo, chunk_repo)

    query = NormalizedQuery(
        raw_text="GET /v1/users",
        method="GET",
        path_pattern="/v1/users",
    )
    result = await lookup.lookup(query, revision_id, workspace_id)

    assert result.matched_entity_type == "operation"
    assert result.chunk_ids == []
