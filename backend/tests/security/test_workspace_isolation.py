"""Workspace isolation tests.

Verifies that Qdrant filter construction always includes workspace_id,
ensuring tenant isolation is enforced at the infrastructure layer.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from qdrant_client.http import models as qmodels

from fetch.infrastructure.qdrant.repository import (
    _assert_tenant_scoped,
    _build_tenant_filter,
)

_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")
_REVISION_ID = UUID("00000000-0000-0000-0000-000000000002")
_PROFILE_VERSION = "v1"


def test_qdrant_filter_always_includes_workspace_id() -> None:
    """Verify the Qdrant filter builder always includes workspace_id."""
    f = _build_tenant_filter(
        workspace_id=_WORKSPACE_ID,
        revision_id=_REVISION_ID,
        embedding_profile_version=_PROFILE_VERSION,
    )
    keys = {c.key for c in (f.must or []) if isinstance(c, qmodels.FieldCondition)}
    assert "workspace_id" in keys


def test_qdrant_filter_always_includes_revision_id() -> None:
    """Verify the Qdrant filter builder always includes revision_id."""
    f = _build_tenant_filter(
        workspace_id=_WORKSPACE_ID,
        revision_id=_REVISION_ID,
        embedding_profile_version=_PROFILE_VERSION,
    )
    keys = {c.key for c in (f.must or []) if isinstance(c, qmodels.FieldCondition)}
    assert "revision_id" in keys


def test_qdrant_filter_workspace_value_matches() -> None:
    """Verify workspace_id filter condition contains the correct value."""
    f = _build_tenant_filter(
        workspace_id=_WORKSPACE_ID,
        revision_id=_REVISION_ID,
        embedding_profile_version=_PROFILE_VERSION,
    )
    workspace_conditions = [
        c
        for c in (f.must or [])
        if isinstance(c, qmodels.FieldCondition) and c.key == "workspace_id"
    ]
    assert len(workspace_conditions) == 1
    assert workspace_conditions[0].match.value == str(_WORKSPACE_ID)


def test_assert_tenant_scoped_passes_valid_filter() -> None:
    """_assert_tenant_scoped must not raise when all required fields are present."""
    f = _build_tenant_filter(
        workspace_id=_WORKSPACE_ID,
        revision_id=_REVISION_ID,
        embedding_profile_version=_PROFILE_VERSION,
    )
    _assert_tenant_scoped(f)  # must not raise


def test_assert_tenant_scoped_raises_when_workspace_missing() -> None:
    """_assert_tenant_scoped must raise AssertionError when workspace_id is absent."""
    f = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="revision_id",
                match=qmodels.MatchValue(value=str(_REVISION_ID)),
            ),
            qmodels.FieldCondition(
                key="embedding_profile_version",
                match=qmodels.MatchValue(value=_PROFILE_VERSION),
            ),
        ]
    )
    with pytest.raises(AssertionError, match="workspace_id"):
        _assert_tenant_scoped(f)


def test_qdrant_filter_with_source_ids() -> None:
    """Source_ids filter is added in addition to required tenant fields."""
    source_id = UUID("00000000-0000-0000-0000-000000000099")
    f = _build_tenant_filter(
        workspace_id=_WORKSPACE_ID,
        revision_id=_REVISION_ID,
        embedding_profile_version=_PROFILE_VERSION,
        source_ids=[source_id],
    )
    keys = {c.key for c in (f.must or []) if isinstance(c, qmodels.FieldCondition)}
    assert "workspace_id" in keys
    assert "source_id" in keys
