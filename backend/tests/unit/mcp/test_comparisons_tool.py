"""Unit tests for fetch_compare_versions tool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from fetch.domain.entities import OperationDiff, VersionDiff


def _make_version_diff(source_id: object) -> VersionDiff:
    from uuid import UUID

    return VersionDiff(
        source_id=UUID(str(source_id)),
        revision_a_id=uuid4(),
        revision_b_id=uuid4(),
        revision_a_version="1.0.0",
        revision_b_version="1.1.0",
        operations_added=[
            OperationDiff(
                operation_id=uuid4(),
                method="POST",
                path="/v1/widgets",
                change_type="added",
                changed_fields=[],
            )
        ],
        operations_removed=[],
        operations_changed=[],
        schemas_added=[],
        schemas_removed=[],
        schemas_changed=[],
        auth_added=[],
        auth_removed=[],
        summary="1 operations added",
    )


@pytest.mark.asyncio
async def test_fetch_compare_versions_returns_diff() -> None:
    source_id = uuid4()
    diff = _make_version_diff(source_id)

    mock_svc = MagicMock()
    mock_svc.diff = AsyncMock(return_value=diff)

    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    with (
        patch(
            "fetch.mcp.tools.comparisons.get_session",
            return_value=mock_session,
        ),
        patch(
            "fetch.mcp.tools.comparisons.get_version_diff_service",
            return_value=mock_svc,
        ),
    ):
        from fetch.mcp.tools.comparisons import fetch_compare_versions

        result = await fetch_compare_versions(
            source_id=str(source_id),
            version_a="1.0.0",
            version_b="1.1.0",
        )

    assert isinstance(result, dict)
    assert "source_id" in result
    assert isinstance(result["source_id"], str)
    assert "revision_a_id" in result
    assert isinstance(result["revision_a_id"], str)
    assert "revision_b_id" in result
    assert isinstance(result["revision_b_id"], str)
    assert "summary" in result
    assert result["summary"] == "1 operations added"
    assert "operations_added" in result
    assert isinstance(result["operations_added"], list)
    assert len(result["operations_added"]) == 1
    assert "operations_removed" in result
    assert "operations_changed" in result
    assert "schemas_added" in result
    assert "auth_added" in result
    assert "auth_removed" in result

    op = result["operations_added"][0]
    assert "operation_id" in op
    assert isinstance(op["operation_id"], str)
    assert op["method"] == "POST"
    assert op["change_type"] == "added"
