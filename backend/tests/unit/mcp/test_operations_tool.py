"""Unit tests for fetch_get_operation tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import ApiOperation
from fetch.domain.enums import HttpMethod


def _make_operation() -> ApiOperation:
    return ApiOperation(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        method=HttpMethod.GET,
        path="/v1/items",
        path_normalized="/v1/items",
        operation_id="listItems",
        summary="List items",
        description="Returns all items.",
        tags=["items"],
        deprecated=False,
        logical_key="src:1.0:GET:/v1/items",
        source_pointer="#/paths/~1v1~1items/get",
        security_requirements=[],
    )


@pytest.mark.asyncio
async def test_fetch_get_operation_returns_full_fields() -> None:
    op = _make_operation()

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=op)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.operations.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.operations.PgOperationRepository",
            return_value=mock_repo,
        ),
    ):
        from fetch.mcp.tools.operations import fetch_get_operation

        result = await fetch_get_operation(operation_id=str(op.id))

    assert isinstance(result, dict)
    assert result["operation_id"] == str(op.id)
    assert isinstance(result["operation_id"], str)
    assert result["method"] == "GET"
    assert result["path"] == "/v1/items"
    assert "description" in result
    assert "tags" in result


@pytest.mark.asyncio
async def test_fetch_get_operation_not_found() -> None:
    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.operations.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.operations.PgOperationRepository",
            return_value=mock_repo,
        ),
    ):
        from fetch.mcp.tools.operations import fetch_get_operation

        result = await fetch_get_operation(operation_id=str(uuid4()))

    assert isinstance(result, dict)
    assert "error" in result
