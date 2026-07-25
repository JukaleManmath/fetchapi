"""Unit tests for RRFFusion.

Pure Python — no external services required.
"""

from __future__ import annotations

import math
from uuid import uuid4

from fetch.application.retrieval.fusion import FusionConfig, RRFFusion
from fetch.infrastructure.qdrant.models import ChunkHit

# ── helpers ────────────────────────────────────────────────────────────────────


def _hit(score: float = 1.0, payload: dict | None = None) -> ChunkHit:
    return ChunkHit(
        chunk_id=uuid4(),
        score=score,
        payload=payload if payload is not None else {"text": "x"},
    )


# ── empty input ────────────────────────────────────────────────────────────────


def test_empty_ranked_lists_returns_empty() -> None:
    result = RRFFusion().fuse([])
    assert result == []


def test_all_lists_empty_returns_empty() -> None:
    result = RRFFusion().fuse([[], [], []])
    assert result == []


# ── single list ────────────────────────────────────────────────────────────────


def test_single_list_order_preserved_by_rrf_score() -> None:
    """A single ranked list must return hits in the same order (rank 1 = highest RRF)."""
    hits = [_hit(), _hit(), _hit()]
    result = RRFFusion().fuse([hits])

    assert len(result) == 3
    assert result[0].chunk_id == hits[0].chunk_id
    assert result[1].chunk_id == hits[1].chunk_id
    assert result[2].chunk_id == hits[2].chunk_id
    # Scores must be strictly descending.
    assert result[0].score > result[1].score > result[2].score


def test_single_list_rrf_formula() -> None:
    """Doc at rank 1 in a single-list input must have score == 1 / (60 + 1)."""
    hit = _hit()
    result = RRFFusion().fuse([[hit]])

    assert len(result) == 1
    expected = 1.0 / (60 + 1)
    assert math.isclose(result[0].score, expected, rel_tol=1e-9)


# ── two lists with overlap ─────────────────────────────────────────────────────


def test_overlapping_doc_accumulates_scores() -> None:
    """A doc appearing in two lists must have a higher score than any exclusive doc."""
    shared = _hit()
    exclusive_a = _hit()
    exclusive_b = _hit()

    list_a = [shared, exclusive_a]
    list_b = [shared, exclusive_b]

    result = RRFFusion().fuse([list_a, list_b])

    result_by_id = {h.chunk_id: h for h in result}

    assert result[0].chunk_id == shared.chunk_id, "shared doc must rank first"
    assert (
        result_by_id[shared.chunk_id].score > result_by_id[exclusive_a.chunk_id].score
    )
    assert (
        result_by_id[shared.chunk_id].score > result_by_id[exclusive_b.chunk_id].score
    )


# ── two lists with no overlap ──────────────────────────────────────────────────


def test_no_overlap_all_docs_returned_sorted() -> None:
    """When no doc appears in both lists all docs must be present, scores descending."""
    list_a = [_hit(), _hit()]
    list_b = [_hit(), _hit()]

    result = RRFFusion().fuse([list_a, list_b])

    assert len(result) == 4
    for i in range(len(result) - 1):
        assert result[i].score >= result[i + 1].score


# ── top_k truncation ───────────────────────────────────────────────────────────


def test_top_k_truncation() -> None:
    hits = [_hit() for _ in range(10)]
    config = FusionConfig(top_k=3)
    result = RRFFusion().fuse([hits], config=config)

    assert len(result) == 3


def test_top_k_larger_than_total_docs_returns_all() -> None:
    hits = [_hit() for _ in range(3)]
    config = FusionConfig(top_k=100)
    result = RRFFusion().fuse([hits], config=config)

    assert len(result) == 3


# ── custom k value ─────────────────────────────────────────────────────────────


def test_custom_k_changes_scores() -> None:
    """Using k=0 should produce score == 1/rank, which differs from k=60 default."""
    hit = _hit()

    result_default = RRFFusion().fuse([[hit]])
    result_k0 = RRFFusion().fuse([[hit]], config=FusionConfig(k=0))

    assert math.isclose(result_default[0].score, 1.0 / 61, rel_tol=1e-9)
    assert math.isclose(result_k0[0].score, 1.0 / 1, rel_tol=1e-9)


def test_custom_k_formula_exact() -> None:
    """Verify rrf_score = 1/(k+1) for a single doc at rank 1 with custom k."""
    hit = _hit()
    config = FusionConfig(k=10)
    result = RRFFusion().fuse([[hit]], config=config)

    expected = 1.0 / (10 + 1)
    assert math.isclose(result[0].score, expected, rel_tol=1e-9)


# ── payload ownership ──────────────────────────────────────────────────────────


def test_payload_taken_from_first_list_containing_doc() -> None:
    """The payload attached to the fused hit must come from the first list."""
    chunk_id = uuid4()

    hit_in_first = ChunkHit(chunk_id=chunk_id, score=0.9, payload={"source": "first"})
    hit_in_second = ChunkHit(chunk_id=chunk_id, score=0.5, payload={"source": "second"})

    result = RRFFusion().fuse([[hit_in_first], [hit_in_second]])

    assert len(result) == 1
    assert result[0].payload == {"source": "first"}


def test_payload_taken_from_first_list_even_when_not_top_ranked() -> None:
    """Payload ownership is determined by list order, not rank within a list."""
    chunk_id = uuid4()

    # chunk_id appears at rank 2 in list_a and rank 1 in list_b.
    list_a = [_hit(), ChunkHit(chunk_id=chunk_id, score=0.5, payload={"list": "a"})]
    list_b = [ChunkHit(chunk_id=chunk_id, score=0.9, payload={"list": "b"})]

    result = RRFFusion().fuse([list_a, list_b])

    result_by_id = {h.chunk_id: h for h in result}
    # list_a comes first, so payload from list_a must win.
    assert result_by_id[chunk_id].payload == {"list": "a"}


# ── deduplication ──────────────────────────────────────────────────────────────


def test_each_chunk_id_appears_at_most_once() -> None:
    chunk_id = uuid4()
    hit = ChunkHit(chunk_id=chunk_id, score=1.0, payload={})

    result = RRFFusion().fuse([[hit, hit], [hit]])

    ids = [h.chunk_id for h in result]
    assert ids.count(chunk_id) == 1
