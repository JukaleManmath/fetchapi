"""Unit tests for chunk text builders and relation builder.

No external services — all inputs are domain entities built directly.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

from fetch.domain.entities import (
    ApiOperation,
    ApiParameter,
    ApiRequestBody,
    ApiResponse,
    ApiSchema,
    AuthScheme,
    ErrorDefinition,
)
from fetch.domain.enums import (
    AuthSchemeType,
    ChunkRelationType,
    ChunkType,
    HttpMethod,
    ParameterLocation,
)
from fetch.infrastructure.embeddings.chunker import (
    build_auth_chunk,
    build_chunk_relations,
    build_error_chunk,
    build_operation_chunk,
    build_schema_chunk,
)
from fetch.infrastructure.embeddings.profile import EmbeddingProfile

# ── Fixtures ──────────────────────────────────────────────────────────────────

WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")
SOURCE_ID = uuid4()
REVISION_ID = uuid4()
API_VERSION = "2025-01-01"

PROFILE = EmbeddingProfile(
    id=uuid4(),
    version="v1",
    dense_model_id="nvidia/nv-embed-v2",
    dense_dimension=4096,
    sparse_model_id="Qdrant/bm25",
    collection_name="fetch_chunks_v1",
    distance_metric="cosine",
)


def _make_operation(
    method: HttpMethod = HttpMethod.POST,
    path: str = "/v1/customers",
    summary: str = "Create a customer",
    description: str | None = "Creates a new customer object.",
    tags: list[str] | None = None,
    parameters: list[ApiParameter] | None = None,
    request_body: ApiRequestBody | None = None,
    responses: list[ApiResponse] | None = None,
    security_requirements: list[dict[str, list[str]]] | None = None,
    deprecated: bool = False,
) -> ApiOperation:
    op_id = uuid4()
    return ApiOperation(
        id=op_id,
        revision_id=REVISION_ID,
        workspace_id=WORKSPACE_ID,
        method=method,
        path=path,
        path_normalized=path.rstrip("/").lower(),
        operation_id="createCustomer",
        summary=summary,
        description=description,
        tags=tags or ["Customers"],
        deprecated=deprecated,
        logical_key=f"{SOURCE_ID}:{API_VERSION}:{method}:{path}",
        source_pointer=f"#/paths/{path}/{method.lower()}",
        parameters=parameters or [],
        request_body=request_body,
        responses=responses or [],
        security_requirements=security_requirements or [],
    )


def _make_parameter(
    name: str = "email",
    location: ParameterLocation = ParameterLocation.QUERY,
    required: bool = True,
    description: str | None = "Customer email address",
) -> ApiParameter:
    return ApiParameter(
        id=uuid4(),
        revision_id=REVISION_ID,
        operation_id=None,
        name=name,
        location=location,
        required=required,
        deprecated=False,
        description=description,
        schema_json=json.dumps({"type": "string"}),
        example_json=None,
        source_pointer=None,
    )


def _make_schema(
    name: str = "Customer",
    description: str | None = "A customer object",
    properties: dict | None = None,
    required: list[str] | None = None,
) -> ApiSchema:
    schema_obj: dict = {"type": "object"}
    if properties:
        schema_obj["properties"] = properties
    if required:
        schema_obj["required"] = required
    return ApiSchema(
        id=uuid4(),
        revision_id=REVISION_ID,
        workspace_id=WORKSPACE_ID,
        name=name,
        description=description,
        schema_json=json.dumps(schema_obj),
        source_pointer=f"#/components/schemas/{name}",
        logical_key=f"{SOURCE_ID}:{API_VERSION}:{name}",
        nullable=False,
        deprecated=False,
    )


def _make_auth(
    name: str = "bearerAuth",
    scheme_type: AuthSchemeType = AuthSchemeType.HTTP,
    details: dict | None = None,
) -> AuthScheme:
    return AuthScheme(
        id=uuid4(),
        revision_id=REVISION_ID,
        workspace_id=WORKSPACE_ID,
        name=name,
        scheme_type=scheme_type,
        description="Bearer token authentication",
        details_json=json.dumps(details or {"scheme": "bearer", "bearerFormat": "JWT"}),
    )


def _make_error(
    status_code: str = "422",
    error_code: str | None = "validation_error",
    title: str | None = "Validation Error",
    description: str | None = "The request body is invalid.",
    operation_id: UUID | None = None,
) -> ErrorDefinition:
    return ErrorDefinition(
        id=uuid4(),
        revision_id=REVISION_ID,
        workspace_id=WORKSPACE_ID,
        operation_id=operation_id,
        status_code=status_code,
        error_code=error_code,
        title=title,
        description=description,
        source_pointer=None,
    )


# ── Operation chunk tests ─────────────────────────────────────────────────────


def test_build_operation_chunk_includes_method_and_path():
    op = _make_operation()
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "POST" in chunk.text
    assert "/v1/customers" in chunk.text


def test_build_operation_chunk_includes_summary():
    op = _make_operation(summary="Create a customer")
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "Create a customer" in chunk.text


def test_build_operation_chunk_includes_description():
    op = _make_operation(description="Creates a new customer object.")
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "Creates a new customer object." in chunk.text


def test_build_operation_chunk_no_auth_label():
    op = _make_operation()
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "Auth: None" in chunk.text


def test_build_operation_chunk_with_auth_names():
    op = _make_operation()
    chunk = build_operation_chunk(
        op, ["bearerAuth", "apiKey"], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE
    )
    assert "bearerAuth" in chunk.text
    assert "apiKey" in chunk.text


def test_build_operation_chunk_required_params_listed():
    params = [
        _make_parameter("email", required=True),
        _make_parameter("name", required=False),
    ]
    op = _make_operation(parameters=params)
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "email" in chunk.text
    assert "required" in chunk.text


def test_build_operation_chunk_truncates_long_param_list():
    params = [_make_parameter(f"param_{i}", required=False) for i in range(15)]
    op = _make_operation(parameters=params)
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "and 5 more parameters" in chunk.text


def test_build_operation_chunk_includes_responses():
    responses = [
        ApiResponse(
            id=uuid4(),
            operation_id=uuid4(),
            status_code="200",
            description="Success",
            content_schemas={},
            headers={},
        ),
        ApiResponse(
            id=uuid4(),
            operation_id=uuid4(),
            status_code="400",
            description="Bad request",
            content_schemas={},
            headers={},
        ),
    ]
    op = _make_operation(responses=responses)
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "200" in chunk.text
    assert "400" in chunk.text


def test_build_operation_chunk_deprecated_flag():
    op = _make_operation(deprecated=True)
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "DEPRECATED" in chunk.text


def test_build_operation_chunk_type():
    op = _make_operation()
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert chunk.chunk_type == ChunkType.OPERATION_SUMMARY


def test_build_operation_chunk_entity_fields():
    op = _make_operation()
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert chunk.entity_type == "operation"
    assert chunk.entity_id == op.id
    assert chunk.method == "POST"
    assert chunk.path == "/v1/customers"
    assert chunk.revision_id == REVISION_ID
    assert chunk.workspace_id == WORKSPACE_ID
    assert chunk.source_id == SOURCE_ID


def test_build_operation_chunk_qdrant_point_id_equals_chunk_id():
    op = _make_operation()
    chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert chunk.qdrant_point_id == chunk.id


def test_build_operation_chunk_content_hash_is_deterministic():
    op = _make_operation()
    chunk1 = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    chunk2 = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    # Text is deterministic; hashes must match even though UUIDs differ.
    assert chunk1.content_hash == chunk2.content_hash


def test_build_operation_chunk_hash_changes_with_profile_version():
    op = _make_operation()
    profile_v2 = EmbeddingProfile(
        id=PROFILE.id,
        version="v2",
        dense_model_id=PROFILE.dense_model_id,
        dense_dimension=PROFILE.dense_dimension,
        sparse_model_id=PROFILE.sparse_model_id,
        collection_name=PROFILE.collection_name,
        distance_metric=PROFILE.distance_metric,
    )
    chunk_v1 = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    chunk_v2 = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, profile_v2)
    assert chunk_v1.content_hash != chunk_v2.content_hash


# ── Schema chunk tests ────────────────────────────────────────────────────────


def test_build_schema_chunk_includes_name():
    schema = _make_schema("Customer")
    chunk = build_schema_chunk(schema, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "Customer" in chunk.text


def test_build_schema_chunk_includes_description():
    schema = _make_schema(description="A customer object")
    chunk = build_schema_chunk(schema, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "A customer object" in chunk.text


def test_build_schema_chunk_lists_properties():
    schema = _make_schema(
        properties={
            "email": {"type": "string", "description": "Email address"},
            "name": {"type": "string"},
        },
        required=["email"],
    )
    chunk = build_schema_chunk(schema, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "email" in chunk.text
    assert "required" in chunk.text
    assert "name" in chunk.text


def test_build_schema_chunk_type():
    schema = _make_schema()
    chunk = build_schema_chunk(schema, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert chunk.chunk_type == ChunkType.SCHEMA_DETAIL
    assert chunk.entity_type == "schema"


def test_build_schema_chunk_nullable_flag():
    schema = _make_schema()
    object.__setattr__(schema, "nullable", True)
    chunk = build_schema_chunk(schema, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "Nullable: yes" in chunk.text


# ── Auth chunk tests ──────────────────────────────────────────────────────────


def test_build_auth_chunk_includes_name_and_type():
    auth = _make_auth("bearerAuth", AuthSchemeType.HTTP)
    chunk = build_auth_chunk(auth, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "bearerAuth" in chunk.text
    assert "http" in chunk.text


def test_build_auth_chunk_http_scheme_details():
    auth = _make_auth(
        details={"scheme": "bearer", "bearerFormat": "JWT"}
    )
    chunk = build_auth_chunk(auth, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "bearer" in chunk.text
    assert "JWT" in chunk.text


def test_build_auth_chunk_api_key_details():
    auth = _make_auth(
        name="apiKey",
        scheme_type=AuthSchemeType.API_KEY,
        details={"in": "header", "name": "X-API-Key"},
    )
    chunk = build_auth_chunk(auth, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "header" in chunk.text
    assert "X-API-Key" in chunk.text


def test_build_auth_chunk_type():
    auth = _make_auth()
    chunk = build_auth_chunk(auth, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert chunk.chunk_type == ChunkType.AUTH_SCHEME
    assert chunk.entity_type == "auth_scheme"


# ── Error chunk tests ─────────────────────────────────────────────────────────


def test_build_error_chunk_includes_status_code():
    error = _make_error(status_code="422")
    chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "422" in chunk.text


def test_build_error_chunk_includes_error_code():
    error = _make_error(error_code="card_declined")
    chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "card_declined" in chunk.text


def test_build_error_chunk_includes_description():
    error = _make_error(description="The card was declined.")
    chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "The card was declined." in chunk.text


def test_build_error_chunk_type():
    error = _make_error()
    chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert chunk.chunk_type == ChunkType.ERROR_DEFINITION
    assert chunk.entity_type == "error_definition"


def test_build_error_chunk_status_codes_field():
    error = _make_error(status_code="404")
    chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    assert "404" in chunk.status_codes


# ── Relation tests ────────────────────────────────────────────────────────────


def test_build_chunk_relations_operation_requires_auth():
    auth = _make_auth("bearerAuth")
    auth_chunk = build_auth_chunk(auth, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    auth_chunks_by_name = {"bearerAuth": auth_chunk}

    op = _make_operation(security_requirements=[{"bearerAuth": []}])
    op_chunk = build_operation_chunk(op, ["bearerAuth"], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)

    relations = build_chunk_relations(
        op_chunk=op_chunk,
        operation=op,
        schema_chunks_by_entity_id={},
        auth_chunks_by_name=auth_chunks_by_name,
        error_chunks_by_entity_id={},
    )

    auth_rels = [r for r in relations if r.relation_type == ChunkRelationType.OPERATION_REQUIRES_AUTH]
    assert len(auth_rels) == 1
    assert auth_rels[0].from_chunk_id == op_chunk.id
    assert auth_rels[0].to_chunk_id == auth_chunk.id


def test_build_chunk_relations_operation_has_error():
    error = _make_error()
    error_chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)
    error_chunks_by_id = {error.id: error_chunk}

    op = _make_operation()
    op_chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)

    relations = build_chunk_relations(
        op_chunk=op_chunk,
        operation=op,
        schema_chunks_by_entity_id={},
        auth_chunks_by_name={},
        error_chunks_by_entity_id=error_chunks_by_id,
    )

    error_rels = [r for r in relations if r.relation_type == ChunkRelationType.OPERATION_HAS_ERROR]
    assert len(error_rels) == 1
    assert error_rels[0].from_chunk_id == op_chunk.id
    assert error_rels[0].to_chunk_id == error_chunk.id


def test_build_chunk_relations_no_relations_when_empty():
    op = _make_operation()
    op_chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)

    relations = build_chunk_relations(
        op_chunk=op_chunk,
        operation=op,
        schema_chunks_by_entity_id={},
        auth_chunks_by_name={},
        error_chunks_by_entity_id={},
    )

    assert relations == []


def test_build_chunk_relations_revision_id_propagated():
    error = _make_error()
    error_chunk = build_error_chunk(error, API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)

    op = _make_operation()
    op_chunk = build_operation_chunk(op, [], API_VERSION, SOURCE_ID, WORKSPACE_ID, PROFILE)

    relations = build_chunk_relations(
        op_chunk=op_chunk,
        operation=op,
        schema_chunks_by_entity_id={},
        auth_chunks_by_name={},
        error_chunks_by_entity_id={error.id: error_chunk},
    )

    for rel in relations:
        assert rel.revision_id == REVISION_ID
