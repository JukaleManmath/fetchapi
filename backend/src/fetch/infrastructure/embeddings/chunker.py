"""Chunk text builders for each canonical entity type.

Each builder produces one Chunk from one domain entity. The text is the
retrieval projection — what gets embedded and stored in Qdrant. It is
written to be readable by both a dense encoder and a sparse BM25 index.

Design rules (ARCHITECTURE.md §9):
- Never drop required operation facts to hit a token target.
- One operation_summary chunk per operation (Phase 2 baseline).
- Large-op splitting is deferred to Phase 3 after token measurement.
- Guide section chunks are deferred to Phase 4 (website ingestion).
- content_hash = SHA-256(text + profile_version) for idempotency.
"""

from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID, uuid4

from fetch.domain.entities import (
    ApiOperation,
    ApiSchema,
    AuthScheme,
    Chunk,
    ChunkRelation,
    ErrorDefinition,
)
from fetch.domain.enums import ChunkRelationType, ChunkType
from fetch.infrastructure.embeddings.profile import EmbeddingProfile

logger = logging.getLogger(__name__)

# Max parameters to list inline before truncating with "and N more".
_MAX_INLINE_PARAMS = 10


# ── Content hash ──────────────────────────────────────────────────────────────


def _content_hash(text: str, profile_version: str) -> str:
    """SHA-256 of text + profile_version — stable across runs for the same input."""
    payload = f"{profile_version}:{text}".encode()
    return hashlib.sha256(payload).hexdigest()


# ── Operation chunk ───────────────────────────────────────────────────────────


def build_operation_chunk(
    operation: ApiOperation,
    auth_scheme_names: list[str],
    api_version: str | None,
    source_id: UUID,
    workspace_id: UUID,
    profile: EmbeddingProfile,
) -> Chunk:
    """Build one operation_summary chunk from an ApiOperation.

    Includes all required facts so the chunk is self-contained for retrieval:
    method, path, description, auth, parameters, request body, responses.
    """
    lines: list[str] = []

    # Header line — the most important signal for exact lookup.
    summary = operation.summary or operation.operation_id or ""
    header = f"{operation.method} {operation.path}"
    if summary:
        header = f"{header} — {summary}"
    lines.append(header)

    if operation.description:
        lines.append(operation.description.strip())

    if operation.deprecated:
        lines.append("DEPRECATED")

    # Auth
    if auth_scheme_names:
        lines.append(f"Auth: {', '.join(auth_scheme_names)}")
    else:
        lines.append("Auth: None")

    # Tags
    if operation.tags:
        lines.append(f"Tags: {', '.join(operation.tags)}")

    # Parameters
    all_params = operation.parameters
    required_params = [p for p in all_params if p.required]
    optional_params = [p for p in all_params if not p.required]

    if all_params:
        total = len(all_params)
        req_count = len(required_params)
        lines.append(f"Parameters ({total} total, {req_count} required):")
        inline = (required_params + optional_params)[:_MAX_INLINE_PARAMS]
        for param in inline:
            req_label = "required" if param.required else "optional"
            desc = f" — {param.description.strip()}" if param.description else ""
            lines.append(f"  {param.name} ({param.location}, {req_label}){desc}")
        remaining = total - len(inline)
        if remaining > 0:
            lines.append(f"  ... and {remaining} more parameters")

    # Request body
    if operation.request_body:
        rb = operation.request_body
        content_types = list(rb.content_schemas.keys())
        ct_str = ", ".join(content_types) if content_types else "unknown"
        req_label = "required" if rb.required else "optional"
        lines.append(f"Request body ({ct_str}, {req_label}):")
        if rb.description:
            lines.append(f"  {rb.description.strip()}")
        # Extract required fields from the first JSON schema.
        for _ct, schema_str in rb.content_schemas.items():
            try:
                schema = json.loads(schema_str)
                required_fields = schema.get("required", [])
                if required_fields:
                    lines.append(f"  Required fields: {', '.join(required_fields)}")
            except (json.JSONDecodeError, AttributeError):
                pass
            break  # Only inspect the first content type.

    # Responses
    if operation.responses:
        lines.append("Responses:")
        for resp in operation.responses:
            desc = f" — {resp.description.strip()}" if resp.description else ""
            lines.append(f"  {resp.status_code}{desc}")

    text = "\n".join(lines)
    chunk_id = uuid4()

    status_codes = [r.status_code for r in operation.responses]

    return Chunk(
        id=chunk_id,
        revision_id=operation.revision_id,
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_type=ChunkType.OPERATION_SUMMARY,
        entity_type="operation",
        entity_id=operation.id,
        title=header,
        text=text,
        content_hash=_content_hash(text, profile.version),
        embedding_profile_version=str(profile.id),
        qdrant_point_id=chunk_id,
        method=operation.method.value,
        path=operation.path,
        operation_id=operation.operation_id,
        tags=list(operation.tags),
        status_codes=status_codes,
        api_version=api_version,
        source_pointer=operation.source_pointer,
    )


# ── Schema chunk ──────────────────────────────────────────────────────────────


def build_schema_chunk(
    schema: ApiSchema,
    api_version: str | None,
    source_id: UUID,
    workspace_id: UUID,
    profile: EmbeddingProfile,
) -> Chunk:
    """Build one schema_detail chunk from an ApiSchema."""
    lines: list[str] = [f"Schema: {schema.name}"]

    if schema.description:
        lines.append(schema.description.strip())

    if schema.nullable:
        lines.append("Nullable: yes")

    if schema.deprecated:
        lines.append("DEPRECATED")

    # Extract properties from the stored JSON schema.
    try:
        schema_obj = json.loads(schema.schema_json)
        properties = schema_obj.get("properties", {})
        required_fields = set(schema_obj.get("required", []))
        schema_type = schema_obj.get("type", "")
        if schema_type:
            lines.append(f"Type: {schema_type}")
        if properties:
            lines.append("Properties:")
            for prop_name, prop_def in properties.items():
                if not isinstance(prop_def, dict):
                    continue
                req_label = "required" if prop_name in required_fields else "optional"
                prop_type = prop_def.get("type", "")
                prop_desc = prop_def.get("description", "")
                type_str = f", {prop_type}" if prop_type else ""
                desc_str = f" — {prop_desc.strip()}" if prop_desc else ""
                lines.append(f"  {prop_name} ({req_label}{type_str}){desc_str}")
    except (json.JSONDecodeError, AttributeError):
        pass

    text = "\n".join(lines)
    chunk_id = uuid4()

    return Chunk(
        id=chunk_id,
        revision_id=schema.revision_id,
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_type=ChunkType.SCHEMA_DETAIL,
        entity_type="schema",
        entity_id=schema.id,
        title=f"Schema: {schema.name}",
        text=text,
        content_hash=_content_hash(text, profile.version),
        embedding_profile_version=str(profile.id),
        qdrant_point_id=chunk_id,
        method=None,
        path=None,
        operation_id=None,
        api_version=api_version,
        source_pointer=schema.source_pointer,
    )


# ── Auth scheme chunk ─────────────────────────────────────────────────────────


def build_auth_chunk(
    auth_scheme: AuthScheme,
    api_version: str | None,
    source_id: UUID,
    workspace_id: UUID,
    profile: EmbeddingProfile,
) -> Chunk:
    """Build one auth_scheme chunk from an AuthScheme."""
    lines: list[str] = [f"Auth: {auth_scheme.name} ({auth_scheme.scheme_type})"]

    if auth_scheme.description:
        lines.append(auth_scheme.description.strip())

    # Surface scheme-specific details from details_json.
    try:
        details = json.loads(auth_scheme.details_json)
        if isinstance(details, dict):
            # apiKey: show where it goes and the header/param name.
            if auth_scheme.scheme_type == "apiKey":
                location = details.get("in", "")
                name = details.get("name", "")
                if location and name:
                    lines.append(f"Location: {location}, Name: {name}")
            # http: show the scheme (bearer, basic, etc.)
            elif auth_scheme.scheme_type == "http":
                scheme = details.get("scheme", "")
                bearer_format = details.get("bearerFormat", "")
                if scheme:
                    desc = f"Scheme: {scheme}"
                    if bearer_format:
                        desc += f" ({bearer_format})"
                    lines.append(desc)
            # oauth2: list flow types and scopes.
            elif auth_scheme.scheme_type == "oauth2":
                flows = details.get("flows", {})
                if flows:
                    flow_names = list(flows.keys())
                    lines.append(f"OAuth2 flows: {', '.join(flow_names)}")
                    for flow_name, flow_def in flows.items():
                        if not isinstance(flow_def, dict):
                            continue
                        scopes = flow_def.get("scopes", {})
                        if scopes:
                            scope_list = ", ".join(list(scopes.keys())[:10])
                            lines.append(f"  {flow_name} scopes: {scope_list}")
    except (json.JSONDecodeError, AttributeError):
        pass

    text = "\n".join(lines)
    chunk_id = uuid4()

    return Chunk(
        id=chunk_id,
        revision_id=auth_scheme.revision_id,
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_type=ChunkType.AUTH_SCHEME,
        entity_type="auth_scheme",
        entity_id=auth_scheme.id,
        title=f"Auth: {auth_scheme.name}",
        text=text,
        content_hash=_content_hash(text, profile.version),
        embedding_profile_version=str(profile.id),
        qdrant_point_id=chunk_id,
        method=None,
        path=None,
        operation_id=None,
        api_version=api_version,
    )


# ── Error definition chunk ────────────────────────────────────────────────────


def build_error_chunk(
    error: ErrorDefinition,
    api_version: str | None,
    source_id: UUID,
    workspace_id: UUID,
    profile: EmbeddingProfile,
) -> Chunk:
    """Build one error_definition chunk from an ErrorDefinition."""
    title_parts = []
    if error.status_code:
        title_parts.append(f"Error {error.status_code}")
    if error.error_code:
        title_parts.append(error.error_code)
    if error.title:
        title_parts.append(error.title)
    title = " — ".join(title_parts) if title_parts else "Error"

    lines: list[str] = [title]
    if error.description:
        lines.append(error.description.strip())

    status_codes = [error.status_code] if error.status_code else []
    text = "\n".join(lines)
    chunk_id = uuid4()

    return Chunk(
        id=chunk_id,
        revision_id=error.revision_id,
        workspace_id=workspace_id,
        source_id=source_id,
        chunk_type=ChunkType.ERROR_DEFINITION,
        entity_type="error_definition",
        entity_id=error.id,
        title=title,
        text=text,
        content_hash=_content_hash(text, profile.version),
        embedding_profile_version=str(profile.id),
        qdrant_point_id=chunk_id,
        method=None,
        path=None,
        operation_id=None,
        status_codes=status_codes,
        api_version=api_version,
        source_pointer=error.source_pointer,
    )


# ── Chunk relations ───────────────────────────────────────────────────────────


def build_chunk_relations(
    op_chunk: Chunk,
    operation: ApiOperation,
    schema_chunks_by_entity_id: dict[UUID, Chunk],
    auth_chunks_by_name: dict[str, Chunk],
    error_chunks_by_entity_id: dict[UUID, Chunk],
) -> list[ChunkRelation]:
    """Build typed relations from one operation chunk to related chunks.

    Relations are used during Phase 3 relationship expansion — they allow
    deterministic context addition after reranking without a second vector query.
    """
    relations: list[ChunkRelation] = []

    def _make_rel(
        from_chunk: Chunk,
        to_chunk: Chunk,
        relation_type: ChunkRelationType,
    ) -> ChunkRelation:
        return ChunkRelation(
            id=uuid4(),
            from_chunk_id=from_chunk.id,
            to_chunk_id=to_chunk.id,
            relation_type=relation_type,
            revision_id=from_chunk.revision_id,
        )

    # OPERATION_REQUIRES_AUTH — one relation per required security scheme.
    for req in operation.security_requirements:
        for scheme_name in req:
            auth_chunk = auth_chunks_by_name.get(scheme_name)
            if auth_chunk is not None:
                relations.append(
                    _make_rel(op_chunk, auth_chunk, ChunkRelationType.OPERATION_REQUIRES_AUTH)
                )

    # OPERATION_USES_SCHEMA — schemas referenced in the request body.
    if operation.request_body:
        for _ct, schema_str in operation.request_body.content_schemas.items():
            try:
                schema_obj = json.loads(schema_str)
                ref = schema_obj.get("$ref", "")
                schema_name = ref.split("/")[-1] if ref else ""
                # Match by entity_id isn't directly available here; match via
                # chunks that were built from schemas. We look for a schema
                # chunk whose title matches the ref name.
                for _entity_id, schema_chunk in schema_chunks_by_entity_id.items():
                    if schema_name and schema_name in schema_chunk.title:
                        relations.append(
                            _make_rel(
                                op_chunk, schema_chunk, ChunkRelationType.OPERATION_USES_SCHEMA
                            )
                        )
                        break
            except (json.JSONDecodeError, AttributeError):
                pass

    # OPERATION_RETURNS_SCHEMA — schemas referenced in responses.
    for resp in operation.responses:
        for _ct, schema_str in resp.content_schemas.items():
            try:
                schema_obj = json.loads(schema_str)
                ref = schema_obj.get("$ref", "")
                schema_name = ref.split("/")[-1] if ref else ""
                for _entity_id, schema_chunk in schema_chunks_by_entity_id.items():
                    if schema_name and schema_name in schema_chunk.title:
                        relations.append(
                            _make_rel(
                                op_chunk,
                                schema_chunk,
                                ChunkRelationType.OPERATION_RETURNS_SCHEMA,
                            )
                        )
                        break
            except (json.JSONDecodeError, AttributeError):
                pass

    # OPERATION_HAS_ERROR — error definitions linked to this operation.
    for _entity_id, error_chunk in error_chunks_by_entity_id.items():
        relations.append(
            _make_rel(op_chunk, error_chunk, ChunkRelationType.OPERATION_HAS_ERROR)
        )

    return relations
