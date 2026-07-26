<div align="center">

<img src="docs/assets/logo.svg" alt="FetchAPI" width="120" />

# FetchAPI

**Give your AI coding assistant accurate, citation-backed knowledge of any API.**

Upload an OpenAPI spec. Connect your editor via MCP. Ask questions, generate integration code, validate requests - all grounded in the actual spec, not model memory.

[![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docs.docker.com/)
[![OpenAPI](https://img.shields.io/badge/OpenAPI-3.0%20%7C%203.1-6BA539?logo=openapiinitiative&logoColor=white)](https://www.openapis.org/)
[![MCP](https://img.shields.io/badge/MCP-Compatible-7C3AED)](https://modelcontextprotocol.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[Quick Start](#quick-start) · [MCP Tools](#mcp-tools) · [HTTP API](#http-api) · [Architecture](#architecture) · [Evaluation](#evaluation) · [Development](#development)

</div>

---

AI coding assistants hallucinate API details because they rely on training data that is months or years out of date. FetchAPI fixes this: it ingests your OpenAPI spec, builds a hybrid retrieval index, and exposes nine MCP tools that give your editor structured, citation-backed knowledge of that API. Every answer cites the exact spec section it came from. When the evidence is insufficient, it says so.

No cloud, no subscription, no pasted docs. Runs entirely in Docker.

---

## Quick Start

**Prerequisites:** Docker and an API key for an OpenAI-compatible LLM/embeddings provider ([NVIDIA NIM](https://build.nvidia.com/) free tier works).

```bash
git clone https://github.com/your-username/fetchapi.git
cd fetchapi
cp .env.example .env
# Set LLM_API_KEY, EMBEDDINGS_API_KEY, RERANKER_API_KEY in .env
docker compose up -d
```

**Upload a spec:**

```bash
# From a file
curl -X POST http://localhost:8000/v1/sources/openapi/upload \
  -F "name=My API" \
  -F "file=@openapi.yaml"

# From a URL
curl -X POST http://localhost:8000/v1/sources/openapi/url \
  -H "Content-Type: application/json" \
  -d '{"name": "Stripe", "url": "https://raw.githubusercontent.com/stripe/openapi/master/openapi/spec3.json"}'

# Poll until ACTIVE
curl http://localhost:8000/v1/jobs/{job_id}
```

**Connect your editor:**

<details>
<summary><strong>Claude Desktop</strong></summary>

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "fetchapi": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Restart Claude Desktop.

</details>

<details>
<summary><strong>Cursor</strong></summary>

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "fetchapi": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

</details>

<details>
<summary><strong>VS Code + Cline</strong></summary>

Open Cline settings and add under MCP Servers:

```json
{
  "fetchapi": {
    "url": "http://localhost:8000/mcp"
  }
}
```

</details>

The web UI is available at [http://localhost:3000](http://localhost:3000).

---

## MCP Tools

Nine focused tools, each backed by a typed application service:

| Tool | Description |
|---|---|
| `fetch_list_sources` | List all ingested APIs with their active revision status |
| `fetch_search_docs` | Hybrid search across operations, schemas, and auth schemes |
| `fetch_get_operation` | Full operation detail - parameters, request body, responses, auth |
| `fetch_get_schema` | Full schema definition with types, constraints, and examples |
| `fetch_get_auth` | Auth schemes - type, scopes, header names, token endpoint |
| `fetch_generate_integration` | Generate spec-grounded integration code in Python, TypeScript, or Java |
| `fetch_validate_request` | Validate a curl command against the documented schema |
| `fetch_explain_error` | Explain a status code in context of the spec |
| `fetch_compare_versions` | Structural diff of two revisions - added, removed, and changed |

---

## HTTP API

Base URL: `http://localhost:8000` · Docs: [`/docs`](http://localhost:8000/docs)

**Sources and ingestion**

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/sources/openapi/upload` | Upload an OpenAPI file |
| `POST` | `/v1/sources/openapi/url` | Ingest from a remote URL |
| `GET` | `/v1/sources` | List all sources |
| `GET` | `/v1/sources/{id}` | Get source with active revision |
| `GET` | `/v1/jobs/{id}` | Poll ingestion job status |
| `POST` | `/v1/jobs/{id}/cancel` | Cancel an in-progress ingestion |
| `DELETE` | `/v1/sources/{id}` | Delete a source and all its data |

**Canonical entities**

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/v1/sources/{id}/operations` | List operations for the active revision |
| `GET` | `/v1/operations/{id}` | Full operation detail |
| `GET` | `/v1/sources/{id}/schemas` | List schemas for the active revision |
| `GET` | `/v1/schemas/{id}` | Full schema detail |
| `GET` | `/v1/sources/{id}/auth` | Auth schemes for the active revision |

**Retrieval and Q&A**

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/query` | Grounded Q&A with SSE streaming and citations |
| `POST` | `/v1/sources/{id}/search` | Hybrid retrieval - ranked chunks with scores |

**Generation and validation**

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/v1/integrations/generate` | Generate integration code for an operation |
| `POST` | `/v1/validate/request` | Validate a curl command against the spec |

---

## Architecture

<div align="center">
<img src="docs/assets/architecture.svg" alt="FetchAPI Architecture" width="100%"/>
</div>

**Storage**

| Store | Role |
|---|---|
| PostgreSQL | Source of truth - sources, revisions, canonical entities, ingestion jobs, chunks |
| Qdrant | Rebuildable retrieval index - dense vectors (1024-dim) + BM25 text index |
| MinIO | Immutable raw spec snapshots - SHA-256 addressed, S3-compatible |
| Redis | Retrieval and answer cache; distributed locks for stampede prevention |

**Layers**

```
API / MCP entrypoints        parse input, resolve auth, call one service, map errors
         ↓
Application services         orchestrate use cases; depend on domain protocols only
         ↓
Domain entities / protocols  entities, enums, errors, pure validation - zero framework imports
         ↑
Infrastructure adapters      PostgreSQL, Qdrant, Redis, MinIO, OpenAPI parsing, LLM/embeddings
```

The domain layer has zero imports of FastAPI, SQLAlchemy, Qdrant, Redis, or any LLM SDK. Infrastructure adapters convert exceptions to stable domain errors before crossing the boundary.

---

## Ingestion Pipeline

Every spec goes through an 11-stage idempotent background pipeline:

```
QUEUED → FETCHING → SNAPSHOTTING → PARSING → VALIDATING → NORMALIZING
       → CHUNKING → EMBEDDING → INDEXING → VERIFYING → ACTIVE
```

| Stage | What happens |
|---|---|
| **FETCHING** | Load raw bytes from file upload or URL with timeout and size limits |
| **SNAPSHOTTING** | SHA-256 hash; immutable copy stored in MinIO. Same content = no-op |
| **PARSING** | Safe YAML/JSON load with alias-expansion cap; `$ref` resolution with SSRF protection and cycle detection |
| **VALIDATING** | OpenAPI 3.0/3.1 schema validation via `openapi-spec-validator` |
| **NORMALIZING** | Extract canonical entities: operations, schemas, auth schemes, servers, examples, error definitions |
| **CHUNKING** | Build self-contained text projections per entity; save chunks and typed relations to PostgreSQL |
| **EMBEDDING** | Batch-embed all chunks via the configured embeddings provider (default: NVIDIA NIM, 1024-dim) |
| **INDEXING** | Upsert into Qdrant with deterministic point IDs; BM25 text index on the `text` payload field |
| **VERIFYING** | Point count in Qdrant must match expected chunk count before activation |
| **ACTIVE** | Atomic revision activation - previous revision marked SUPERSEDED in the same transaction |

A failed revision never replaces an active one.

---

## Security

- **SSRF protection** - external `$ref` URLs are resolved to IP and checked against blocked ranges (loopback, RFC-1918, link-local, metadata service) before any network request
- **DoS prevention** - YAML alias expansion capped at 100 per document, enforced before `yaml.safe_load()` constructs Python objects
- **External ref limits** - max 3 hops, 1 MB per document, 10-second timeout
- **No code execution** - generated code is syntax-validated against the spec schema, never executed on the host
- **No secret logging** - API keys and auth headers extracted from specs are redacted before any log write
- **Workspace isolation** - every Qdrant query includes mandatory `workspace_id` and `revision_id` payload filters
- **Prompt injection boundary** - ingested documentation is treated as untrusted evidence; the system prompt separates retrieved context from user instructions

Security tests covering SSRF (3 tests), workspace isolation (6 tests), and prompt injection (8 tests) run in CI on every push.

---

## Evaluation

Evaluation runners require a live stack with ingested sources and are not part of the CI test suite.

```bash
python evals/runners/retrieval_benchmark.py --source-id <id> --mode hybrid
python evals/runners/answer_benchmark.py --source-id <id>
python evals/runners/ablation_runner.py --source-id <id>
```

**Retrieval** - hybrid mode (dense + BM25 + RRF), 25 questions per dataset:

| Dataset | Recall@5 | Recall@10 | MRR |
|---|---|---|---|
| Petstore (19 ops) | **1.00** | **1.00** | **0.96** |
| Stripe (587 ops) | **0.84** | **0.84** | **0.81** |
| GitHub GHES (962 ops) | **0.84** | **0.84** | **0.74** |

**Answer** - Petstore (30 questions, 5 abstention):

| Metric | Result | Target |
|---|---|---|
| Citation accuracy | **0.72** | ≥ 0.70 |
| Abstention accuracy | **0.87** | ≥ 0.85 |
| Groundedness | **0.72** | ≥ 0.70 |

Reranking is disabled by default (`RERANK_LIMIT=0`). Set `RERANK_LIMIT=10` with a compatible reranker endpoint to enable the cross-encoder stage.

---

## Configuration

All configuration via environment variables. Copy `.env.example` to `.env`.

<details>
<summary><strong>Using a different LLM provider</strong></summary>

FetchAPI defaults to NVIDIA NIM but works with any OpenAI-compatible provider:

```env
# OpenAI
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL_ID=gpt-4o

# Ollama (local)
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL_ID=llama3.1:70b
```

The same swap applies to embeddings via `EMBEDDINGS_BASE_URL`, `EMBEDDINGS_API_KEY`, `EMBEDDINGS_MODEL_ID`. No code changes required.

</details>

<details>
<summary><strong>Key environment variables</strong></summary>

```env
# LLM
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
LLM_API_KEY=your-key
LLM_MODEL_ID=meta/llama-3.1-70b-instruct

# Embeddings
EMBEDDINGS_BASE_URL=https://integrate.api.nvidia.com/v1
EMBEDDINGS_API_KEY=your-key
EMBEDDINGS_MODEL_ID=nvidia/nv-embedqa-e5-v5
EMBEDDINGS_DIMENSION=1024

# Reranker
RERANKER_BASE_URL=https://integrate.api.nvidia.com/v1
RERANKER_API_KEY=your-key
RERANKER_MODEL_ID=nvidia/nv-rerankqa-mistral-4b-v3

# Ingestion limits
WORKER_INGESTION_MAX_ALIASES=100
WORKER_INGESTION_MAX_RETRIES=3

# External $ref limits
EXT_REF_MAX_HOPS=3
EXT_REF_MAX_BYTES=1048576
EXT_REF_TIMEOUT_SECONDS=10
```

See [`.env.example`](.env.example) for the full list.

</details>

---

## Development

```bash
make install-dev    # create backend/.venv and install all dependencies
make up             # start infrastructure (PostgreSQL, Qdrant, Redis, MinIO)
make migrate        # run Alembic migrations
make run            # start FastAPI with hot reload at localhost:8000
```

**Tests**

```bash
make test-unit          # unit tests - no infrastructure required
make test-integration   # integration tests - requires running stack
make test               # full suite
make test-cov           # with coverage report
```

**Code quality**

```bash
make lint           # ruff check
make format         # ruff format
make typecheck      # mypy
make check          # all three (run before committing)
```

---

## Project Structure

```
fetchapi/
├── backend/
│   ├── src/fetch/
│   │   ├── api/v1/           # HTTP route handlers
│   │   ├── application/      # Use cases: ingestion, retrieval, queries, generation, validation
│   │   ├── domain/           # Entities, enums, errors, protocols - zero framework imports
│   │   ├── infrastructure/   # PostgreSQL, Qdrant, Redis, MinIO, OpenAPI parsing, LLM/embeddings
│   │   ├── mcp/              # MCP server and 9 tools via Streamable HTTP
│   │   └── config.py         # Pydantic settings
│   ├── migrations/           # Alembic migrations
│   └── tests/
│       ├── unit/             # Pure logic - no infrastructure
│       ├── integration/      # End-to-end against real stack
│       ├── security/         # SSRF, workspace isolation, prompt injection
│       └── fixtures/         # Edge-case OpenAPI specs
├── examples/
│   ├── petstore/             # OpenAPI 3.0.4 - 19 operations
│   ├── github/               # GHES 3.12 - 962 operations, 765 schemas
│   └── stripe/               # Stripe API - 587 operations, 1,431 schemas
├── evals/
│   ├── datasets/             # 90-question eval datasets
│   ├── runners/              # retrieval, answer, validation, and ablation runners
│   └── thresholds.json       # regression thresholds
├── frontend/                 # Next.js 15 web UI
├── infra/
│   └── compose.yaml          # PostgreSQL · Qdrant · Redis · MinIO · FastAPI
├── docs/assets/              # Logo and architecture SVGs
├── .env.example
└── Makefile
```

---

## Limitations

- OpenAPI 3.0.x and 3.1.x only - no Swagger 2.0, GraphQL, AsyncAPI, or Postman Collections
- File and URL ingestion only - no HTML documentation crawling or PDF support
- Single workspace, single tenant - no multi-user access control
- Generated code is syntax-validated against the spec, not executed or runtime-tested
- Cross-encoder reranking disabled by default - requires a paid NIM tier or self-hosted endpoint

---

## License

[MIT](LICENSE)
