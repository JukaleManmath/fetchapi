"""Structured exact lookup against PostgreSQL.

Given a NormalizedQuery, performs targeted point-reads against the canonical
entity tables (operations, schemas) and resolves the corresponding chunk IDs.
No vector search is involved — this is purely an index lookup.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from uuid import UUID

from fetch.application.retrieval.normalizer import NormalizedQuery
from fetch.domain.protocols import (
    ChunkRepository,
    OperationRepository,
    SchemaRepository,
)

# Segments that look like {param} placeholders are preserved as-is.
_PARAM_SEGMENT_RE = re.compile(r"^\{[a-zA-Z0-9_]+\}$")


def _normalize_path(path: str) -> str:
    """Normalize a URL path for exact lookup against api_operations.path_normalized.

    Rules (mirrors the ingestion-time normalization):
    - Strip one trailing slash (e.g. ``/v1/users/`` → ``/v1/users``).
    - Lowercase static segments (non-parameter segments).
    - Preserve ``{param}`` placeholders verbatim.
    - Leading slash is kept.
    """
    path = path.rstrip("/") or "/"
    segments = path.split("/")
    normalized_segments = []
    for segment in segments:
        if _PARAM_SEGMENT_RE.match(segment):
            normalized_segments.append(segment)
        else:
            normalized_segments.append(segment.lower())
    return "/".join(normalized_segments)


@dataclass(frozen=True)
class ExactLookupResult:
    """Value object returned by :class:`ExactLookup`.

    ``chunk_ids`` contains all chunk IDs that directly correspond to the
    matched entity.  When no entity matched, all fields are empty/None.
    """

    chunk_ids: list[UUID] = field(default_factory=list)
    matched_entity_type: str | None = None
    matched_entity_id: UUID | None = None


_EMPTY_RESULT = ExactLookupResult()


class ExactLookup:
    """Runs exact PostgreSQL lookups for structured identifiers in a query.

    Priority order:
    1. method + path_pattern → ``OperationRepository.find_by_method_path``
    2. operation_id          → ``OperationRepository.find_by_operation_id``
    3. schema_names          → ``SchemaRepository.find_by_name`` (first match wins)
    4. No match              → returns an empty :class:`ExactLookupResult`

    For every matched entity, chunk IDs are resolved via
    ``ChunkRepository.find_chunk_ids_by_entity``.
    """

    def __init__(
        self,
        operation_repo: OperationRepository,
        schema_repo: SchemaRepository,
        chunk_repo: ChunkRepository,
    ) -> None:
        self._operation_repo = operation_repo
        self._schema_repo = schema_repo
        self._chunk_repo = chunk_repo

    async def lookup(
        self,
        query: NormalizedQuery,
        revision_id: UUID,
        workspace_id: UUID,
    ) -> ExactLookupResult:
        """Return an :class:`ExactLookupResult` for the best exact match.

        ``workspace_id`` is accepted for future tenant-scoping but the current
        queries delegate tenant isolation to ``revision_id`` (revisions belong
        to a single workspace).
        """
        # 1. Method + path match — most specific signal.
        if query.method and query.path_pattern:
            path_normalized = _normalize_path(query.path_pattern)
            operation = await self._operation_repo.find_by_method_path(
                revision_id, query.method, path_normalized
            )
            if operation is not None:
                return await self._build_operation_result(revision_id, operation.id)

        # 2. operation_id match.
        if query.operation_id:
            operation = await self._operation_repo.find_by_operation_id(
                revision_id, query.operation_id
            )
            if operation is not None:
                return await self._build_operation_result(revision_id, operation.id)

        # 3. Schema name match — iterate names, return on first hit.
        for name in query.schema_names:
            schema = await self._schema_repo.find_by_name(revision_id, name)
            if schema is not None:
                chunk_ids = await self._chunk_repo.find_chunk_ids_by_entity(
                    revision_id, "schema", schema.id
                )
                return ExactLookupResult(
                    chunk_ids=chunk_ids,
                    matched_entity_type="schema",
                    matched_entity_id=schema.id,
                )

        return _EMPTY_RESULT

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _build_operation_result(
        self, revision_id: UUID, entity_id: UUID
    ) -> ExactLookupResult:
        chunk_ids = await self._chunk_repo.find_chunk_ids_by_entity(
            revision_id, "operation", entity_id
        )
        return ExactLookupResult(
            chunk_ids=chunk_ids,
            matched_entity_type="operation",
            matched_entity_id=entity_id,
        )
