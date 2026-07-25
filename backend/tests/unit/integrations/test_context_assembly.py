"""Unit tests for IntegrationContextAssembler."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from fetch.application.integrations.loader import IntegrationContextAssembler
from fetch.domain.entities import ApiOperation, ApiServer, AuthScheme
from fetch.domain.enums import AuthSchemeType, HttpMethod
from fetch.domain.errors import IntegrationContextError

_REVISION_ID = uuid4()
_WORKSPACE_ID = uuid4()
_OP_ID = uuid4()


def _make_operation() -> ApiOperation:
    return ApiOperation(
        id=_OP_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        method=HttpMethod.GET,
        path="/v1/items",
        path_normalized="/v1/items",
        operation_id=None,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key="src:1.0:GET:/v1/items",
        source_pointer=None,
        security_requirements=[],
    )


def _make_server(url: str = "https://api.example.com") -> ApiServer:
    return ApiServer(
        id=uuid4(),
        revision_id=_REVISION_ID,
        url=url,
        description=None,
        variables={},
    )


def _make_assembler(
    operation: ApiOperation | None = None,
    servers: list[ApiServer] | None = None,
    auth_schemes: list[AuthScheme] | None = None,
) -> IntegrationContextAssembler:
    operation_repo = AsyncMock()
    operation_repo.get = AsyncMock(return_value=operation)

    server_repo = AsyncMock()
    server_repo.list_by_revision = AsyncMock(return_value=servers or [])

    auth_scheme_repo = AsyncMock()
    auth_scheme_repo.list_by_revision = AsyncMock(return_value=auth_schemes or [])

    parameter_repo = AsyncMock()
    parameter_repo.list_by_operation = AsyncMock(return_value=[])

    request_body_repo = AsyncMock()
    request_body_repo.get_by_operation = AsyncMock(return_value=None)

    response_repo = AsyncMock()
    response_repo.list_by_operation = AsyncMock(return_value=[])

    example_repo = AsyncMock()
    example_repo.find_by_operation = AsyncMock(return_value=[])

    error_repo = AsyncMock()
    error_repo.find_by_operation = AsyncMock(return_value=[])

    return IntegrationContextAssembler(
        operation_repo=operation_repo,
        server_repo=server_repo,
        auth_scheme_repo=auth_scheme_repo,
        parameter_repo=parameter_repo,
        request_body_repo=request_body_repo,
        response_repo=response_repo,
        example_repo=example_repo,
        error_repo=error_repo,
    )


@pytest.mark.asyncio
async def test_load_returns_context() -> None:
    op = _make_operation()
    server = _make_server("https://api.example.com")
    assembler = _make_assembler(operation=op, servers=[server])
    ctx = await assembler.load(_OP_ID, _REVISION_ID, _WORKSPACE_ID)
    assert ctx.operation == op
    assert ctx.base_url == "https://api.example.com"


@pytest.mark.asyncio
async def test_load_raises_when_operation_not_found() -> None:
    assembler = _make_assembler(operation=None)
    with pytest.raises(IntegrationContextError):
        await assembler.load(_OP_ID, _REVISION_ID, _WORKSPACE_ID)


@pytest.mark.asyncio
async def test_load_uses_first_server_url() -> None:
    op = _make_operation()
    servers = [
        _make_server("https://first.example.com"),
        _make_server("https://second.example.com"),
    ]
    assembler = _make_assembler(operation=op, servers=servers)
    ctx = await assembler.load(_OP_ID, _REVISION_ID, _WORKSPACE_ID)
    assert ctx.base_url == "https://first.example.com"


@pytest.mark.asyncio
async def test_load_filters_auth_by_security_requirements() -> None:
    import json

    op = ApiOperation(
        id=_OP_ID,
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        method=HttpMethod.POST,
        path="/v1/orders",
        path_normalized="/v1/orders",
        operation_id=None,
        summary=None,
        description=None,
        tags=[],
        deprecated=False,
        logical_key="src:1.0:POST:/v1/orders",
        source_pointer=None,
        security_requirements=[{"bearerAuth": []}],
    )

    scheme_a = AuthScheme(
        id=uuid4(),
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        name="bearerAuth",
        scheme_type=AuthSchemeType.HTTP,
        description=None,
        details_json=json.dumps({"scheme": "bearer"}),
    )
    scheme_b = AuthScheme(
        id=uuid4(),
        revision_id=_REVISION_ID,
        workspace_id=_WORKSPACE_ID,
        name="apiKey",
        scheme_type=AuthSchemeType.API_KEY,
        description=None,
        details_json=json.dumps({"in": "header", "name": "X-API-Key"}),
    )

    assembler = _make_assembler(operation=op, auth_schemes=[scheme_a, scheme_b])
    ctx = await assembler.load(_OP_ID, _REVISION_ID, _WORKSPACE_ID)
    assert len(ctx.auth_schemes) == 1
    assert ctx.auth_schemes[0].name == "bearerAuth"
