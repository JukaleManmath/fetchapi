"""Unit tests for RelationshipExpander.

Pure Python — no external services. Both repositories are mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from fetch.application.retrieval.expander import ExpansionConfig, RelationshipExpander
from fetch.domain.entities import Chunk, ChunkRelation
from fetch.domain.enums import ChunkRelationType, ChunkType
from fetch.infrastructure.qdrant.models import ChunkHit

# ── helpers ────────────────────────────────────────────────────────────────────

_REVISION_ID = uuid4()


def _hit(chunk_id: UUID | None = None, score: float = 0.9) -> ChunkHit:
    return ChunkHit(
        chunk_id=chunk_id or uuid4(),
        score=score,
        payload={"text": "some text"},
    )


def _relation(
    from_id: UUID,
    to_id: UUID,
    relation_type: ChunkRelationType = ChunkRelationType.OPERATION_USES_SCHEMA,
) -> ChunkRelation:
    return ChunkRelation(
        id=uuid4(),
        from_chunk_id=from_id,
        to_chunk_id=to_id,
        relation_type=relation_type,
        revision_id=_REVISION_ID,
    )


def _chunk(chunk_id: UUID | None = None) -> Chunk:
    cid = chunk_id or uuid4()
    return Chunk(
        id=cid,
        revision_id=_REVISION_ID,
        workspace_id=uuid4(),
        source_id=uuid4(),
        chunk_type=ChunkType.SCHEMA_DETAIL,
        entity_type="schema",
        entity_id=uuid4(),
        title="Schema chunk",
        text="some schema text",
        content_hash="abc123",
        embedding_profile_version="v1",
        qdrant_point_id=cid,
        method=None,
        path=None,
        operation_id=None,
    )


def _make_repos(
    relations: list[ChunkRelation],
    chunks: list[Chunk],
) -> tuple[AsyncMock, AsyncMock]:
    relation_repo = AsyncMock()
    relation_repo.find_relations_for_chunks = AsyncMock(return_value=relations)

    chunk_repo = AsyncMock()
    chunk_repo.find_chunks_by_ids = AsyncMock(return_value=chunks)

    return relation_repo, chunk_repo


# ── no relations ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_relations_returns_original_hits_unchanged() -> None:
    hit = _hit()
    relation_repo, chunk_repo = _make_repos(relations=[], chunks=[])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID)

    assert result == [hit]
    chunk_repo.find_chunks_by_ids.assert_not_called()


# ── empty hits ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_empty_hits_returns_empty_without_calling_repos() -> None:
    relation_repo, chunk_repo = _make_repos(relations=[], chunks=[])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[], revision_id=_REVISION_ID)

    assert result == []
    relation_repo.find_relations_for_chunks.assert_not_called()
    chunk_repo.find_chunks_by_ids.assert_not_called()


# ── relations found ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_related_chunks_appended_after_original_hits() -> None:
    hit = _hit()
    related_id = uuid4()
    related_chunk = _chunk(chunk_id=related_id)
    rel = _relation(from_id=hit.chunk_id, to_id=related_id)

    relation_repo, chunk_repo = _make_repos(relations=[rel], chunks=[related_chunk])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID)

    assert len(result) == 2
    assert result[0] is hit
    assert result[1].chunk_id == related_id


# ── dedup: chunks already in hits not added again ──────────────────────────────


@pytest.mark.asyncio
async def test_chunk_already_in_hits_is_not_added_again() -> None:
    hit = _hit()
    # A relation that points back to a chunk already in hits.
    rel = _relation(from_id=hit.chunk_id, to_id=hit.chunk_id)

    relation_repo, chunk_repo = _make_repos(relations=[rel], chunks=[])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID)

    # No new IDs to fetch, so find_chunks_by_ids should not be called.
    chunk_repo.find_chunks_by_ids.assert_not_called()
    assert result == [hit]


@pytest.mark.asyncio
async def test_dedup_across_multiple_relations_pointing_to_same_to_id() -> None:
    hit = _hit()
    shared_to_id = uuid4()
    relations = [
        _relation(from_id=hit.chunk_id, to_id=shared_to_id),
        _relation(
            from_id=hit.chunk_id,
            to_id=shared_to_id,
            relation_type=ChunkRelationType.OPERATION_RETURNS_SCHEMA,
        ),
    ]
    related_chunk = _chunk(chunk_id=shared_to_id)

    relation_repo, chunk_repo = _make_repos(relations=relations, chunks=[related_chunk])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID)

    fetched_ids: list[UUID] = chunk_repo.find_chunks_by_ids.call_args.args[0]
    assert fetched_ids.count(shared_to_id) == 1
    assert len(result) == 2


# ── max_expanded_chunks cap ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_max_expanded_chunks_limits_appended_chunks() -> None:
    hit = _hit()
    to_ids = [uuid4() for _ in range(5)]
    relations = [_relation(from_id=hit.chunk_id, to_id=tid) for tid in to_ids]
    # Return only the first 2 (simulating the DB honouring the sliced IDs)
    returned_chunks = [_chunk(chunk_id=to_ids[0]), _chunk(chunk_id=to_ids[1])]

    relation_repo, chunk_repo = _make_repos(relations=relations, chunks=returned_chunks)
    expander = RelationshipExpander(relation_repo, chunk_repo)

    config = ExpansionConfig(max_expanded_chunks=2)
    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID, config=config)

    fetched_ids: list[UUID] = chunk_repo.find_chunks_by_ids.call_args.args[0]
    assert len(fetched_ids) == 2
    assert len(result) == 3  # 1 original + 2 expanded


# ── relation_types filter ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_relation_types_filter_keeps_only_matching_types() -> None:
    hit = _hit()
    schema_id = uuid4()
    auth_id = uuid4()

    relations = [
        _relation(
            from_id=hit.chunk_id,
            to_id=schema_id,
            relation_type=ChunkRelationType.OPERATION_USES_SCHEMA,
        ),
        _relation(
            from_id=hit.chunk_id,
            to_id=auth_id,
            relation_type=ChunkRelationType.OPERATION_REQUIRES_AUTH,
        ),
    ]
    schema_chunk = _chunk(chunk_id=schema_id)

    relation_repo, chunk_repo = _make_repos(relations=relations, chunks=[schema_chunk])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    config = ExpansionConfig(relation_types=[ChunkRelationType.OPERATION_USES_SCHEMA])
    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID, config=config)

    fetched_ids: list[UUID] = chunk_repo.find_chunks_by_ids.call_args.args[0]
    assert auth_id not in fetched_ids
    assert schema_id in fetched_ids
    assert len(result) == 2


@pytest.mark.asyncio
async def test_relation_types_none_follows_all_types() -> None:
    hit = _hit()
    schema_id = uuid4()
    auth_id = uuid4()

    relations = [
        _relation(
            from_id=hit.chunk_id,
            to_id=schema_id,
            relation_type=ChunkRelationType.OPERATION_USES_SCHEMA,
        ),
        _relation(
            from_id=hit.chunk_id,
            to_id=auth_id,
            relation_type=ChunkRelationType.OPERATION_REQUIRES_AUTH,
        ),
    ]
    chunks = [_chunk(chunk_id=schema_id), _chunk(chunk_id=auth_id)]

    relation_repo, chunk_repo = _make_repos(relations=relations, chunks=chunks)
    expander = RelationshipExpander(relation_repo, chunk_repo)

    config = ExpansionConfig(relation_types=None)
    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID, config=config)

    fetched_ids: list[UUID] = chunk_repo.find_chunks_by_ids.call_args.args[0]
    assert schema_id in fetched_ids
    assert auth_id in fetched_ids
    assert len(result) == 3


# ── expanded chunk score ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expanded_chunks_have_score_zero() -> None:
    hit = _hit(score=0.85)
    related_id = uuid4()
    rel = _relation(from_id=hit.chunk_id, to_id=related_id)
    related_chunk = _chunk(chunk_id=related_id)

    relation_repo, chunk_repo = _make_repos(relations=[rel], chunks=[related_chunk])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID)

    expanded = result[1]
    assert expanded.score == 0.0


# ── original hits order preserved ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_original_hit_order_preserved() -> None:
    ids = [uuid4() for _ in range(3)]
    hits = [_hit(chunk_id=cid, score=float(i)) for i, cid in enumerate(ids)]

    relation_repo, chunk_repo = _make_repos(relations=[], chunks=[])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=hits, revision_id=_REVISION_ID)

    assert [r.chunk_id for r in result] == ids


# ── expanded chunk payload ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_expanded_chunk_payload_derived_from_chunk_entity() -> None:
    hit = _hit()
    related_id = uuid4()
    chunk = _chunk(chunk_id=related_id)
    rel = _relation(from_id=hit.chunk_id, to_id=related_id)

    relation_repo, chunk_repo = _make_repos(relations=[rel], chunks=[chunk])
    expander = RelationshipExpander(relation_repo, chunk_repo)

    result = await expander.expand(hits=[hit], revision_id=_REVISION_ID)

    expanded_payload = result[1].payload
    assert expanded_payload["text"] == chunk.text
    assert expanded_payload["title"] == chunk.title
    assert expanded_payload["entity_type"] == chunk.entity_type
    assert expanded_payload["chunk_type"] == chunk.chunk_type.value
    assert expanded_payload["method"] == chunk.method
    assert expanded_payload["path"] == chunk.path
