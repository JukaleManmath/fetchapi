"""Unit tests for ContextPacker."""

import uuid

from fetch.application.retrieval.packer import ContextPacker
from fetch.infrastructure.qdrant.models import ChunkHit


def _chunk_id() -> uuid.UUID:
    return uuid.uuid4()


def _hit(
    chunk_id: uuid.UUID | None = None, score: float = 0.9, **payload_fields
) -> ChunkHit:
    cid = chunk_id or _chunk_id()
    return ChunkHit(chunk_id=cid, score=score, payload=payload_fields)


class TestContextPackerEmptyInput:
    def test_empty_hits_returns_empty_packed_context(self) -> None:
        packer = ContextPacker()
        result = packer.pack([])

        assert result.citations == []
        assert result.context_text == ""
        assert result.source_id_map == {}


class TestContextPackerSingleHit:
    def test_single_hit_assigns_s1(self) -> None:
        cid = _chunk_id()
        hit = _hit(
            chunk_id=cid,
            entity_type="operation",
            title="List users",
            text="Returns a paginated list of users.",
            method="GET",
            path="/users",
        )

        result = ContextPacker().pack([hit])

        assert len(result.citations) == 1
        citation = result.citations[0]
        assert citation.source_id == "S1"
        assert citation.chunk_id == cid

    def test_single_hit_citation_fields(self) -> None:
        cid = _chunk_id()
        entity_id = uuid.uuid4()
        hit = _hit(
            chunk_id=cid,
            entity_type="operation",
            entity_id=str(entity_id),
            title="Create payment",
            text="Creates a new payment.",
            method="POST",
            path="/payments",
            source_url="https://example.com/docs",
            source_pointer="#/paths/~1payments/post",
            api_version="2024-01",
        )

        result = ContextPacker().pack([hit])
        c = result.citations[0]

        assert c.entity_type == "operation"
        assert c.entity_id == entity_id
        assert c.title == "Create payment"
        assert c.content == "Creates a new payment."
        assert c.method == "POST"
        assert c.path == "/payments"
        assert c.source_url == "https://example.com/docs"
        assert c.source_pointer == "#/paths/~1payments/post"
        assert c.api_version == "2024-01"

    def test_single_hit_context_text_contains_s1(self) -> None:
        hit = _hit(entity_type="operation", title="List users", text="Returns users.")

        result = ContextPacker().pack([hit])

        assert "[S1]" in result.context_text

    def test_source_id_map_single(self) -> None:
        cid = _chunk_id()
        hit = _hit(chunk_id=cid)

        result = ContextPacker().pack([hit])

        assert result.source_id_map == {"S1": cid}


class TestContextPackerMultipleHits:
    def test_three_hits_assign_s1_s2_s3_in_order(self) -> None:
        hits = [_hit(title=f"Op {i}", text=f"Content {i}") for i in range(1, 4)]

        result = ContextPacker().pack(hits)

        assert [c.source_id for c in result.citations] == ["S1", "S2", "S3"]

    def test_source_id_map_multiple(self) -> None:
        cids = [_chunk_id(), _chunk_id(), _chunk_id()]
        hits = [_hit(chunk_id=cid) for cid in cids]

        result = ContextPacker().pack(hits)

        assert result.source_id_map == {"S1": cids[0], "S2": cids[1], "S3": cids[2]}

    def test_context_text_contains_all_source_labels(self) -> None:
        hits = [_hit(text=f"Content {i}") for i in range(1, 4)]

        result = ContextPacker().pack(hits)

        assert "[S1]" in result.context_text
        assert "[S2]" in result.context_text
        assert "[S3]" in result.context_text


class TestContextTextFormatting:
    def test_method_path_line_included_when_both_present(self) -> None:
        hit = _hit(
            entity_type="operation",
            title="Delete user",
            text="Deletes the user.",
            method="DELETE",
            path="/users/{id}",
        )

        result = ContextPacker().pack([hit])

        assert "Method: DELETE /users/{id}" in result.context_text

    def test_method_path_line_omitted_when_method_missing(self) -> None:
        hit = _hit(
            entity_type="schema",
            title="User schema",
            text="Describes a user.",
            path="/users",
        )

        result = ContextPacker().pack([hit])

        assert "Method:" not in result.context_text

    def test_method_path_line_omitted_when_path_missing(self) -> None:
        hit = _hit(
            entity_type="schema",
            title="User schema",
            text="Describes a user.",
            method="GET",
        )

        result = ContextPacker().pack([hit])

        assert "Method:" not in result.context_text

    def test_entries_separated_by_blank_line(self) -> None:
        hits = [
            _hit(title="Op 1", text="First."),
            _hit(title="Op 2", text="Second."),
        ]

        result = ContextPacker().pack(hits)

        assert "\n\n" in result.context_text

    def test_context_text_header_format(self) -> None:
        hit = _hit(entity_type="operation", title="List items", text="Lists items.")

        result = ContextPacker().pack([hit])

        assert "[S1] operation — List items" in result.context_text


class TestMissingPayloadFields:
    def test_no_key_error_on_empty_payload(self) -> None:
        hit = ChunkHit(chunk_id=_chunk_id(), score=0.5, payload={})

        # Must not raise
        result = ContextPacker().pack([hit])

        assert len(result.citations) == 1

    def test_entity_id_is_none_when_not_in_payload(self) -> None:
        hit = _hit(entity_type="operation", title="Op", text="Desc.")

        result = ContextPacker().pack([hit])

        assert result.citations[0].entity_id is None

    def test_optional_fields_default_to_none(self) -> None:
        hit = _hit(entity_type="operation", title="Op", text="Desc.")

        result = ContextPacker().pack([hit])
        c = result.citations[0]

        assert c.source_url is None
        assert c.source_pointer is None
        assert c.api_version is None
        assert c.method is None
        assert c.path is None

    def test_invalid_entity_id_string_yields_none(self) -> None:
        hit = _hit(entity_id="not-a-uuid", title="Op", text="Desc.")

        result = ContextPacker().pack([hit])

        assert result.citations[0].entity_id is None
