"""Unit tests for the OpenAPI extractor.

No database, no network, no external services.
"""

import json
from uuid import uuid4

import pytest

from fetch.infrastructure.openapi.extractor import (
    extract_api_title,
    extract_api_version,
    extract_auth_schemes,
    extract_operations,
    extract_schemas,
    extract_servers,
    normalize_path,
    normalize_schema_types,
    extract_schema_json,
    MAX_SCHEMA_DEPTH,
)


REVISION_ID = uuid4()
WORKSPACE_ID = uuid4()
SOURCE_ID = uuid4()


# ── normalize_path ────────────────────────────────────────────────────────────


def test_normalize_path_strips_trailing_slash() -> None:
    assert normalize_path("/v1/customers/") == "/v1/customers"


def test_normalize_path_lowercases_static_segments() -> None:
    assert normalize_path("/v1/Customers") == "/v1/customers"


def test_normalize_path_preserves_path_params() -> None:
    assert normalize_path("/v1/customers/{customerId}") == "/v1/customers/{customerId}"


def test_normalize_path_root() -> None:
    assert normalize_path("/") == "/"


def test_normalize_path_multiple_levels() -> None:
    assert normalize_path("/V1/Users/{Id}/Orders/") == "/v1/users/{Id}/orders"


# ── normalize_schema_types ────────────────────────────────────────────────────


def test_normalize_nullable_type_array() -> None:
    schema = {"type": ["string", "null"], "maxLength": 50}
    result = normalize_schema_types(schema)
    assert result["type"] == "string"
    assert result["nullable"] is True
    assert result["maxLength"] == 50


def test_normalize_non_null_array_type() -> None:
    schema = {"type": ["string", "integer"]}
    result = normalize_schema_types(schema)
    assert result["type"] == ["string", "integer"]
    assert "nullable" not in result


def test_normalize_plain_type_unchanged() -> None:
    schema = {"type": "string"}
    result = normalize_schema_types(schema)
    assert result["type"] == "string"
    assert "nullable" not in result


# ── extract_schema_json depth limit ──────────────────────────────────────────


def test_schema_depth_limit() -> None:
    """Schema nested deeper than MAX_SCHEMA_DEPTH should be replaced with a ref."""
    deep_schema: dict = {"type": "object"}
    node = deep_schema
    for _ in range(MAX_SCHEMA_DEPTH + 2):
        child: dict = {"type": "object", "properties": {"child": {}}}
        node["properties"] = {"child": child}
        node = child

    result = json.loads(extract_schema_json(deep_schema, pointer="#/test"))
    # Root should be present
    assert result["type"] == "object"


def test_schema_cycle_detection() -> None:
    """A seen pointer should be returned as a $ref placeholder, not infinite recursion."""
    schema = {"type": "object", "properties": {"self": {"$ref": "#/self"}}}
    # Should not raise RecursionError
    result = extract_schema_json(schema, pointer="#/self", seen_pointers={"#/self"})
    parsed = json.loads(result)
    assert "$ref" in parsed


# ── extract_servers ───────────────────────────────────────────────────────────


def test_extract_servers_basic() -> None:
    doc = {
        "servers": [
            {"url": "https://api.example.com/v1", "description": "Production"},
            {"url": "https://sandbox.example.com/v1"},
        ]
    }
    servers = extract_servers(doc, REVISION_ID)
    assert len(servers) == 2
    assert servers[0].url == "https://api.example.com/v1"
    assert servers[0].description == "Production"
    assert servers[1].description is None


def test_extract_servers_default_when_missing() -> None:
    servers = extract_servers({}, REVISION_ID)
    assert len(servers) == 1
    assert servers[0].url == "/"


# ── extract_auth_schemes ──────────────────────────────────────────────────────


def test_extract_auth_schemes_apikey() -> None:
    doc = {
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-API-Key",
                }
            }
        }
    }
    schemes = extract_auth_schemes(doc, REVISION_ID, WORKSPACE_ID)
    assert len(schemes) == 1
    assert schemes[0].name == "ApiKeyAuth"
    assert schemes[0].scheme_type.value == "apiKey"
    details = json.loads(schemes[0].details_json)
    assert details["in"] == "header"
    assert details["name"] == "X-API-Key"


def test_extract_auth_schemes_empty() -> None:
    schemes = extract_auth_schemes({}, REVISION_ID, WORKSPACE_ID)
    assert schemes == []


# ── extract_schemas ───────────────────────────────────────────────────────────


def test_extract_schemas_basic() -> None:
    doc = {
        "components": {
            "schemas": {
                "Customer": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "name": {"type": "string"}},
                    "required": ["id"],
                }
            }
        }
    }
    schemas = extract_schemas(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "1.0.0")
    assert len(schemas) == 1
    assert schemas[0].name == "Customer"
    assert schemas[0].nullable is False
    assert schemas[0].deprecated is False
    assert f"{SOURCE_ID}:1.0.0:#/components/schemas/Customer" == schemas[0].logical_key


def test_extract_schemas_nullable_31() -> None:
    doc = {
        "components": {
            "schemas": {
                "MaybeString": {"type": ["string", "null"]}
            }
        }
    }
    schemas = extract_schemas(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "1.0.0")
    assert schemas[0].nullable is True


# ── extract_operations ────────────────────────────────────────────────────────


def test_extract_operations_basic() -> None:
    doc = {
        "paths": {
            "/pets": {
                "get": {
                    "operationId": "listPets",
                    "summary": "List all pets",
                    "tags": ["pets"],
                    "responses": {"200": {"description": "OK"}},
                },
                "post": {
                    "operationId": "createPet",
                    "summary": "Create a pet",
                    "responses": {"201": {"description": "Created"}},
                },
            }
        }
    }
    ops = extract_operations(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "1.0.0")
    assert len(ops) == 2
    methods = {op.method.value for op in ops}
    assert methods == {"GET", "POST"}


def test_extract_operations_logical_key() -> None:
    doc = {
        "paths": {
            "/v1/Customers/": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                }
            }
        }
    }
    ops = extract_operations(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "2.0")
    assert len(ops) == 1
    op = ops[0]
    assert op.path == "/v1/Customers/"
    assert op.path_normalized == "/v1/customers"
    assert op.logical_key == f"{SOURCE_ID}:2.0:GET:/v1/customers"


def test_extract_operations_parameters() -> None:
    doc = {
        "paths": {
            "/pets/{petId}": {
                "parameters": [
                    {
                        "name": "petId",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "get": {
                    "responses": {"200": {"description": "OK"}},
                },
            }
        }
    }
    ops = extract_operations(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "1.0")
    assert len(ops[0].parameters) == 1
    assert ops[0].parameters[0].name == "petId"
    assert ops[0].parameters[0].required is True


def test_extract_operations_request_body() -> None:
    doc = {
        "paths": {
            "/pets": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    "responses": {"201": {"description": "Created"}},
                }
            }
        }
    }
    ops = extract_operations(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "1.0")
    assert ops[0].request_body is not None
    assert ops[0].request_body.required is True
    assert "application/json" in ops[0].request_body.content_schemas


def test_extract_operations_4xx_responses() -> None:
    doc = {
        "paths": {
            "/pets": {
                "get": {
                    "responses": {
                        "200": {"description": "OK"},
                        "404": {"description": "Not found"},
                        "429": {"description": "Rate limited"},
                    }
                }
            }
        }
    }
    ops = extract_operations(doc, REVISION_ID, WORKSPACE_ID, SOURCE_ID, "1.0")
    assert len(ops[0].responses) == 3
    status_codes = {r.status_code for r in ops[0].responses}
    assert status_codes == {"200", "404", "429"}


def test_extract_api_version() -> None:
    assert extract_api_version({"info": {"version": "2025-01-27"}}) == "2025-01-27"
    assert extract_api_version({}) == "0.0.0"


def test_extract_api_title() -> None:
    assert extract_api_title({"info": {"title": "Stripe API"}}) == "Stripe API"
    assert extract_api_title({}) == "Untitled API"
