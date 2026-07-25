"""Unit tests for fetch_get_schema tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import ApiSchema


def _make_schema() -> ApiSchema:
    return ApiSchema(
        id=uuid4(),
        revision_id=uuid4(),
        workspace_id=uuid4(),
        name="Item",
        description="An item object.",
        schema_json='{"type": "object", "properties": {"id": {"type": "string"}}}',
        source_pointer="#/components/schemas/Item",
        logical_key="src:1.0:#/components/schemas/Item",
        nullable=False,
        deprecated=False,
    )


@pytest.mark.asyncio
async def test_fetch_get_schema_returns_full_fields() -> None:
    schema = _make_schema()

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=schema)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.schemas.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.schemas.PgSchemaRepository",
            return_value=mock_repo,
        ),
    ):
        from fetch.mcp.tools.schemas import fetch_get_schema

        result = await fetch_get_schema(schema_id=str(schema.id))

    assert isinstance(result, dict)
    assert result["schema_id"] == str(schema.id)
    assert isinstance(result["schema_id"], str)
    assert result["name"] == "Item"
    assert "schema_json" in result
    assert "description" in result
    assert "nullable" in result
    assert "deprecated" in result


@pytest.mark.asyncio
async def test_fetch_get_schema_not_found() -> None:
    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=None)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("fetch.mcp.tools.schemas.get_session", return_value=mock_session),
        patch(
            "fetch.mcp.tools.schemas.PgSchemaRepository",
            return_value=mock_repo,
        ),
    ):
        from fetch.mcp.tools.schemas import fetch_get_schema

        result = await fetch_get_schema(schema_id=str(uuid4()))

    assert isinstance(result, dict)
    assert "error" in result
