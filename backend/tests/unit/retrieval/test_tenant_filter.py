"""Unit tests for the mandatory tenant-isolation filter helpers.

Both _build_tenant_filter and _assert_tenant_scoped are module-level private
functions in fetch.infrastructure.qdrant.repository.  They are imported directly
to verify the invariants described in ARCHITECTURE.md §7.3.

No external services are used — these tests are pure logic checks.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from qdrant_client.http import models as qmodels

from fetch.infrastructure.qdrant.repository import (
    _assert_tenant_scoped,
    _build_tenant_filter,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _keys_in_must(f: qmodels.Filter) -> set[str]:
    """Return the set of FieldCondition keys present in filter.must."""
    return {c.key for c in (f.must or []) if isinstance(c, qmodels.FieldCondition)}


# ── _build_tenant_filter ──────────────────────────────────────────────────────


def test_build_tenant_filter_contains_all_mandatory_fields() -> None:
    f = _build_tenant_filter(
        workspace_id=uuid4(),
        revision_id=uuid4(),
        embedding_profile_version="v1",
    )

    keys = _keys_in_must(f)
    assert "workspace_id" in keys
    assert "revision_id" in keys
    assert "embedding_profile_version" in keys


def test_build_tenant_filter_without_source_ids_has_exactly_three_conditions() -> None:
    f = _build_tenant_filter(
        workspace_id=uuid4(),
        revision_id=uuid4(),
        embedding_profile_version="v1",
        source_ids=None,
    )

    assert f.must is not None
    assert len(f.must) == 3
    assert "source_id" not in _keys_in_must(f)


def test_build_tenant_filter_with_source_ids_adds_fourth_condition() -> None:
    sid1, sid2 = uuid4(), uuid4()
    f = _build_tenant_filter(
        workspace_id=uuid4(),
        revision_id=uuid4(),
        embedding_profile_version="v1",
        source_ids=[sid1, sid2],
    )

    assert f.must is not None
    assert len(f.must) == 4
    assert "source_id" in _keys_in_must(f)

    # Confirm the source_id condition is a MatchAny containing both UUIDs.
    source_condition = next(
        c
        for c in f.must
        if isinstance(c, qmodels.FieldCondition) and c.key == "source_id"
    )
    assert isinstance(source_condition.match, qmodels.MatchAny)
    assert str(sid1) in source_condition.match.any
    assert str(sid2) in source_condition.match.any


def test_build_tenant_filter_encodes_uuids_as_strings() -> None:
    ws = uuid4()
    rev = uuid4()
    f = _build_tenant_filter(
        workspace_id=ws,
        revision_id=rev,
        embedding_profile_version="v1",
    )

    ws_condition = next(
        c
        for c in (f.must or [])
        if isinstance(c, qmodels.FieldCondition) and c.key == "workspace_id"
    )
    assert isinstance(ws_condition.match, qmodels.MatchValue)
    assert ws_condition.match.value == str(ws)


# ── _assert_tenant_scoped ─────────────────────────────────────────────────────


def test_assert_tenant_scoped_passes_for_complete_filter() -> None:
    f = _build_tenant_filter(
        workspace_id=uuid4(),
        revision_id=uuid4(),
        embedding_profile_version="v1",
    )
    # Must not raise.
    _assert_tenant_scoped(f)


def test_assert_tenant_scoped_raises_if_workspace_id_missing() -> None:
    f = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="revision_id",
                match=qmodels.MatchValue(value=str(uuid4())),
            ),
            qmodels.FieldCondition(
                key="embedding_profile_version",
                match=qmodels.MatchValue(value="v1"),
            ),
        ]
    )
    with pytest.raises(AssertionError, match="workspace_id"):
        _assert_tenant_scoped(f)


def test_assert_tenant_scoped_raises_if_revision_id_missing() -> None:
    f = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="workspace_id",
                match=qmodels.MatchValue(value=str(uuid4())),
            ),
            qmodels.FieldCondition(
                key="embedding_profile_version",
                match=qmodels.MatchValue(value="v1"),
            ),
        ]
    )
    with pytest.raises(AssertionError, match="revision_id"):
        _assert_tenant_scoped(f)


def test_assert_tenant_scoped_raises_if_embedding_profile_version_missing() -> None:
    f = qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="workspace_id",
                match=qmodels.MatchValue(value=str(uuid4())),
            ),
            qmodels.FieldCondition(
                key="revision_id",
                match=qmodels.MatchValue(value=str(uuid4())),
            ),
        ]
    )
    with pytest.raises(AssertionError, match="embedding_profile_version"):
        _assert_tenant_scoped(f)
