# FetchAPI - Architecture and Design Decisions

> **Purpose:** This document is the architectural source of truth for FetchAPI.
> It defines product scope, system boundaries, data ownership, workflows, quality requirements, and accepted trade-offs.
>
> **Implementation rules:** See [`CLAUDE.md`](./CLAUDE.md).

---

## 1. Product Definition

### 1.1 What FetchAPI is

FetchAPI is an **open-source, self-hosted MCP server and API documentation intelligence layer**.

Run it locally with `docker compose up`. Point your AI coding assistant (Cursor, Claude Desktop, VS Code + Cline) at it. Upload an OpenAPI spec. From that point your editor has structured, citation-backed knowledge of that API.

FetchAPI converts documentation sources - initially OpenAPI files and URLs - into a versioned, structured representation that is queryable through:

1. A web application
2. A FastAPI HTTP API
3. An MCP server for AI coding assistants and editors

FetchAPI should help a developer:

- Find the correct endpoint, method, and parameters
- Understand authentication, pagination, rate limits, webhooks, and errors
- Generate integration code grounded in the connected documentation
- Validate a request or code snippet against documented schemas
- Diagnose API errors and malformed requests
- Compare API documentation revisions or versions
- Receive source-linked answers when evidence exists
- Receive an explicit "insufficient documentation" result when evidence does not exist

### 1.2 Product promise

> FetchAPI turns OpenAPI specs into structured, queryable, citation-backed API knowledge that lives in your editor through MCP - no cloud, no subscription, just `docker compose up`.

### 1.3 Primary users

- Developers integrating an unfamiliar third-party API
- Backend engineers maintaining several external integrations
- Developer-support and solutions-engineering teams
- Teams exposing private API documentation to internal coding agents
- AI coding assistants that need structured API knowledge through MCP

### 1.4 Non-goals for v1

FetchAPI is not:

- A general-purpose web search engine
- A replacement for API gateways
- A system that autonomously executes arbitrary generated code
- A secrets manager
- A live API traffic proxy
- An API monitoring platform
- A fully autonomous multi-agent system
- A documentation authoring platform

---

## 2. Core Engineering Principles

1. **Structured data before embeddings.** OpenAPI operations, schemas, authentication schemes, examples, and errors are parsed into a canonical model before retrieval documents are produced.
2. **Deterministic before generative.** Exact endpoint lookup, schema validation, reference resolution, version filtering, and citation mapping are implemented in code. The LLM explains and synthesizes; it does not invent system facts.
3. **Documentation is untrusted evidence.** Crawled text can contain prompt injection, malformed markup, secrets, or hostile links. It is never treated as an instruction to the application or model.
4. **Citations are application data.** The model may emit approved source identifiers, but the server owns the citation metadata and verifies every cited identifier.
5. **Every ingestion creates a revision.** A new index is built and validated before it becomes active. Queries never see a partially ingested revision.
6. **The relational store is the source of truth.** Qdrant is a rebuildable retrieval index, not the authoritative system of record.
7. **Agentic behavior is bounded.** FetchAPI uses an explicit, typed workflow with deterministic tools instead of unconstrained agent loops.
8. **Quality is measured.** Retrieval, grounding, tool selection, code generation, and validation changes must be evaluated against a versioned test set.
9. **Configuration is versioned.** Embedding, sparse retrieval, reranking, prompts, and index schemas have explicit versions so experiments are reproducible.
10. **Build the smallest production-shaped slice.** The MVP is narrow, but its boundaries support durability, observability, security, and future multi-tenancy.

---

## 3. Supported User Workflows

FetchAPI classifies each request into one primary workflow.

| Workflow | Example | Main behavior |
|---|---|---|
| Documentation Q&A | "How does pagination work?" | Retrieve guides and relevant operations; answer with citations |
| Endpoint lookup | "Which endpoint creates a customer?" | Prefer structured operation lookup, then retrieval fallback |
| Authentication guidance | "How do I refresh an OAuth token?" | Retrieve security schemes and authentication guides |
| Integration generation | "Show a Java example for creating a subscription" | Retrieve operation, schemas, auth, and examples; generate and validate code |
| Request validation | "Is this curl request valid?" | Parse request and compare it deterministically with the canonical operation |
| Error diagnosis | "Why am I receiving 422?" | Retrieve documented errors and inspect the supplied request/response |
| Version comparison | "What changed between v1 and v2?" | Compare canonical entities across two source revisions |
| Insufficient evidence | "Does this API guarantee exactly-once delivery?" | Explain that the connected documentation does not establish the claim |

A request may invoke several tools, but it has one workflow owner and a bounded maximum number of steps.

---

## 4. System Context

```text
+------------------------------- Clients --------------------------------+
|                                                                        |
|  Next.js Web UI        HTTP/SDK Consumers        MCP Clients           |
|                                               Claude Code, IDEs        |
+----------------+-------------------+-------------------+---------------+
                 | HTTPS / stream    | HTTPS             | MCP
                 +-------------------+-------------------+
                                     |
                                     v
+--------------------------- FastAPI Application ------------------------+
|                                                                        |
|  REST API      Query Orchestrator      Retrieval Service      MCP      |
|                      |                      |                  Server  |
|                      |                      |                          |
|  Source Service       |         Validation / Code Generation           |
|         |            |                                                  |
+---------+------------+--------------------------------------------------+
          |            |
          | enqueue    | model requests
          v            v
+-----------------+  +---------------------+
| Ingestion       |  | Configurable LLM    |
| Worker          |  | Provider Adapter    |
+--------+--------+  +---------------------+
         |
         +---------------+------------------+---------------------+
         v               v                  v                     v
+--------------+ +--------------+  +--------------+  +----------------+
| PostgreSQL   | | Qdrant       |  | Redis        |  | S3-compatible  |
| source of    | | retrieval    |  | queue/cache  |  | object storage |
| truth        | | index        |  | coordination |  | raw snapshots  |
+--------------+ +--------------+  +--------------+  +----------------+
```

---

## 5. Deployment Units

### 5.1 Web application

- Next.js with TypeScript
- Source connection and ingestion status UI
- Query and integration workspace
- Request debugger
- Citation and retrieval inspector

### 5.2 API application

- FastAPI
- Thin HTTP controllers
- Application services for sources, queries, validation, and versions
- MCP mounted through the official MCP Python SDK using Streamable HTTP
- Provider adapters for LLMs and embedding implementations

### 5.3 Ingestion worker

Background ingestion runs as an `asyncio.create_task()` inside the FastAPI process. The API handler creates source, revision, and job records synchronously, starts the background task, and returns `202 Accepted`. The task runs the full ingestion pipeline independently.

Responsibilities:
- Remote source fetching
- OpenAPI validation and normalization
- Reference resolution
- Canonical entity extraction
- Chunk construction
- Embedding generation
- Qdrant indexing
- Revision validation and activation

**Why not Celery:** FetchAPI is a single-user self-hosted tool. A separate Celery worker process and Redis broker are unnecessary operational complexity for local use. The ingestion service is fully decoupled from the execution mechanism - if a future multi-tenant deployment needs durable distributed workers, swapping `asyncio.create_task` for a task queue is a one-function change. The domain contracts, job state machine, and ingestion logic are unchanged.

### 5.4 PostgreSQL

Authoritative storage for:

- Workspaces and users when authentication is added
- Sources and source configuration
- Source revisions and activation state
- Canonical API entities
- Chunk metadata and relationships
- Ingestion jobs and failures
- Query runs and feedback
- Evaluation cases and results
- Prompt and retrieval configuration versions

### 5.5 Qdrant

Derived search index containing:

- Dense vectors
- Sparse lexical vectors
- Search payload needed for filtering and result display

Qdrant can be rebuilt from PostgreSQL and stored source snapshots.

### 5.6 Redis

Used for:

- Short-lived distributed locks (stampede prevention)
- Rate-limit counters
- Retrieval and answer caches

Redis is not the source of truth for jobs or documents. It is not used as a task broker - ingestion runs as asyncio background tasks.

### 5.7 Object storage

S3-compatible storage holds immutable raw artifacts:

- Uploaded OpenAPI files
- Original HTML pages
- Markdown files
- Crawl manifests
- Normalized snapshots

Use MinIO locally and an S3-compatible provider in deployment.

---

## 6. Canonical Information Model

Embedding raw pages is not sufficient for API integration questions. FetchAPI maintains a canonical intermediate representation (IR).

### 6.1 Core entities

| Entity | Purpose |
|---|---|
| `Workspace` | Isolation boundary; single default workspace in local MVP |
| `ApiSource` | User-configured documentation source |
| `ApiServer` | Active base URLs and server variables per revision |
| `ApiParameter` | Named path/query/header/cookie parameter with type, format, required flag |
| `ApiRequestBody` | Content types and schema references for a request body |
| `ApiResponse` | Status code, content types, schema references, headers |
| `SourceRevision` | Immutable ingestion snapshot and active-version boundary |
| `Document` | A fetched file or page with provenance and content hash |
| `ApiOperation` | HTTP method + path, parameters, body, responses, security, tags |
| `ApiSchema` | Named or anonymous request/response schema |
| `AuthScheme` | API key, bearer, OAuth, OpenID Connect, mutual TLS, or custom guidance |
| `ApiExample` | Request, response, curl, or SDK example with language metadata |
| `GuideSection` | Conceptual documentation such as pagination or rate limiting |
| `ErrorDefinition` | Status code or provider-specific error code and explanation |
| `Chunk` | Retrieval-optimized projection of one or more canonical entities |
| `ChunkRelation` | Typed relationship such as operation - schema or guide - auth scheme |
| `IngestionJob` | Durable state machine for ingestion |
| `QueryRun` | Traceable query, workflow, evidence, output, latency, and feedback |

### 6.2 Identity and revision rules

- Every entity is scoped by `workspace_id`, `source_id`, and `revision_id`.
- A source has exactly one active revision per selected documentation version.
- Stable logical identifiers are derived from source identity plus entity identity, for example `POST /v1/customers`.
- Revision-specific identifiers are immutable UUIDs.
- A new revision never mutates the previous revision.
- Activating a revision is a single PostgreSQL state transition after all required indexes pass validation.

### 6.3 Canonical operation requirements

An `ApiOperation` should preserve, when available:

- HTTP method and normalized path
- `operationId`
- Summary and description
- Tags and resource name
- Servers/base URLs
- Path, query, header, and cookie parameters
- Required flags, types, formats, enums, defaults, and constraints
- Request content types and schemas
- Response status codes, content types, headers, and schemas
- Security requirements and scopes
- Deprecation state
- Examples
- Source location and source pointer

Do not discard structured fields just because equivalent prose exists.

---

## 7. Qdrant Index Design

### 7.1 Collection strategy

Use **one collection per embedding/index profile**, not one collection per API.

Initial collection:

```text
fetch_chunks_v1
```

All tenant, API, source, revision, and document isolation is performed with payload filters. Payload fields used as tenant boundaries must have Qdrant tenant/payload indexes configured.

Why:

- Avoids collection explosion as sources grow
- Supports cross-API discovery when explicitly requested
- Keeps embedding dimensions and index settings consistent
- Matches Qdrant's recommended payload-partitioned multitenancy model
- Makes index migrations explicit through a new collection version

### 7.2 Named vectors

The first benchmark profile uses:

- `dense`: configurable sentence embedding model
- `sparse`: BM25-compatible sparse representation

Baseline models:

- Dense: `nvidia/nv-embedqa-e5-v5` (1024-dim, NVIDIA NIM)
- Sparse: Qdrant BM25 text index on the `text` payload field
- Reranker: `nvidia/nv-rerankqa-mistral-4b-v3` (NVIDIA NIM `/ranking`)

These are **benchmark baselines**, not permanent locks. Model names, dimensions, tokenization, and preprocessing belong to an immutable `embedding_profile_version`.

### 7.3 Point payload

```json
{
  "workspace_id": "uuid",
  "source_id": "uuid",
  "revision_id": "uuid",
  "api_name": "stripe",
  "api_version": "2025-01-27",
  "chunk_id": "uuid",
  "entity_type": "operation",
  "entity_id": "uuid",
  "chunk_type": "operation_summary",
  "method": "POST",
  "path": "/v1/payment_intents",
  "operation_id": "createPaymentIntent",
  "tags": ["PaymentIntents"],
  "language": null,
  "status_codes": ["200", "400", "401"],
  "title": "Create a PaymentIntent",
  "source_url": "https://example.com/docs/payment-intents/create",
  "source_pointer": "#/paths/~1v1~1payment_intents/post",
  "content_hash": "sha256:...",
  "embedding_profile_version": "v1",
  "text": "retrieval projection shown to the model"
}
```

### 7.4 Consistency model

PostgreSQL and object storage are authoritative. Qdrant is eventually consistent during ingestion.

A revision is queryable only after:

1. Canonical extraction succeeds
2. Expected chunk count is recorded
3. Qdrant upsert succeeds
4. Sample points and payload filters are verified
5. The revision is marked `active`

---

## 8. Ingestion Architecture

### 8.1 Source adapter interface

Every source type implements the same lifecycle:

```text
validate_config -> discover -> fetch -> snapshot -> parse -> normalize -> emit canonical entities
```

Implemented adapters:

1. OpenAPI file upload
2. OpenAPI URL

Future adapters:

- Documentation website root URL
- GitHub/Markdown repository
- Postman collection
- GraphQL introspection/schema
- AsyncAPI document

### 8.2 Ingestion state machine

```text
QUEUED
  -> FETCHING
  -> SNAPSHOTTING
  -> PARSING
  -> VALIDATING
  -> NORMALIZING
  -> CHUNKING
  -> EMBEDDING
  -> INDEXING
  -> VERIFYING
  -> ACTIVE

Any state may transition to FAILED.
Cancellation transitions a non-terminal job to CANCELLED.
```

Jobs are idempotent by source configuration hash and content hash. Retrying a failed job must not duplicate entities or points.

**Retry policy:** A failed job always restarts from `QUEUED`. Mid-stage resume is not supported in v1. Maximum retry attempts: configurable via `INGESTION_MAX_RETRIES` (default: 3). After max retries, the job stays `FAILED` and requires manual re-ingestion.

### 8.3 OpenAPI ingestion

1. Parse YAML or JSON with safe loaders.
2. Detect OpenAPI version.
3. Validate OpenAPI 3.0 or 3.1.
4. Resolve internal references and allowed external references with cycle detection.
5. Preserve source pointers before dereferencing.
6. Extract operations, schemas, security schemes, examples, callbacks, webhooks, and servers.
7. Emit canonical entities.
8. Generate retrieval chunks and relationships.

Do not blindly flatten an entire schema tree. Recursive or very large schemas can explode token count and erase reusable schema identity.

### 8.4 Safe remote fetching

All remote fetches must defend against SSRF:

- Allow only `http` and `https`
- Resolve DNS before connecting
- Block loopback, link-local, private, multicast, and cloud metadata ranges
- Revalidate every redirect target
- Set connect/read/total timeouts
- Enforce response-size limits while streaming
- Reject unexpected content types
- Do not forward user-supplied authorization headers
- Record final URL and redirect chain

---

## 9. Chunking and Retrieval Projections

### 9.1 Why a hybrid representation is required

The canonical IR is optimized for correctness. Retrieval chunks are optimized for discoverability. FetchAPI keeps both.

### 9.2 OpenAPI operation chunks

For a small or medium operation, create one `operation_summary` chunk containing:

- Method, path, operation ID, title, and description
- Authentication requirements
- All required parameters
- Concise optional parameter summaries
- Request content types
- Required request fields
- Main success responses
- Common documented error responses
- References to related schema and example entity IDs

For a large operation:

- Keep the operation overview and all required facts together
- Place large request/response schema details in separate `schema` chunks
- Create typed relations from the operation to those chunks
- Expand related chunks after retrieval according to the workflow

### 9.3 Schema chunks

Create schema chunks for:

- Named component schemas
- Large inline schemas
- Request and response shapes that are reused or independently queried

A schema chunk includes properties, required fields, types, formats, constraints, and a bounded nesting depth. It retains a stable pointer to the full canonical schema.

### 9.4 Guide chunks

For HTML or Markdown:

- Split by heading hierarchy
- Include breadcrumb headings in every chunk
- Preserve code blocks with their explanation
- Split oversized sections at paragraph or list boundaries
- Never split in the middle of a code block or table row group
- Store neighboring and parent relationships

### 9.5 Code example chunks

Examples are first-class chunks with metadata:

- Programming language
- SDK or HTTP client
- Related operation
- API version
- Authentication assumptions
- Source URL and heading

### 9.6 Chunk relation types

Named relations stored in `ChunkRelation`:

```text
OPERATION_USES_SCHEMA       operation chunk -> request/response schema chunk
OPERATION_REQUIRES_AUTH     operation chunk -> authentication chunk
OPERATION_RETURNS_SCHEMA    operation chunk -> response schema chunk
OPERATION_HAS_ERROR         operation chunk -> error definition chunk
EXAMPLE_FOR_OPERATION       example chunk -> operation chunk
SCHEMA_REFERENCES_SCHEMA    schema chunk -> nested/referenced schema chunk
GUIDE_COVERS_OPERATION      guide section chunk -> related operation chunk
```

These relations are used during relationship expansion (§11.4) to deterministically add context without semantic retrieval.

### 9.7 Chunk sizing

Chunk size is a benchmarked parameter, not a universal rule.

Initial targets:

- Guide prose: approximately 300-700 tokens
- Operation summaries: complete required context even if larger
- Schema detail chunks: approximately 300-800 tokens
- Code examples: complete executable unit plus explanation

No correctness-critical field is dropped solely to satisfy a token target.

---

## 10. Query Analysis and Orchestration

### 10.1 Intent model

```text
DOC_QA
ENDPOINT_LOOKUP
AUTH_GUIDANCE
INTEGRATION_GENERATION
REQUEST_VALIDATION
ERROR_DIAGNOSIS
VERSION_COMPARE
SCHEMA_LOOKUP
SOURCE_MANAGEMENT
UNSUPPORTED
```

### 10.2 Query signals

Extract before retrieval:

- HTTP method
- Endpoint/path fragment
- `operationId`
- Resource name
- Parameter or schema name
- Status or provider error code
- Programming language and SDK
- API version
- Authentication type
- Desired output form

Use deterministic parsing for explicit identifiers. An LLM classifier may supplement ambiguous natural-language classification, but it does not replace exact extraction.

### 10.3 Bounded workflow

```text
receive request
  -> validate scope and source
  -> classify workflow
  -> extract constraints
  -> run exact lookups
  -> run hybrid retrieval if needed
  -> rerank and expand related evidence
  -> execute deterministic validation when applicable
  -> generate grounded explanation/code when applicable
  -> verify citations and output contract
  -> stream result and persist trace
```

The orchestrator has:

- Typed state
- Explicit tools
- Maximum step count
- Per-tool timeout
- No recursive self-delegation
- No autonomous network access outside approved source tools

### 10.4 Internal tool catalog

```text
list_sources
get_source_revision
find_operation
get_operation
get_schema
get_auth_scheme
get_examples
get_error_definition
search_documentation
get_document_section
validate_http_request
validate_request_body
validate_generated_integration
expand_related_entities
compare_revisions
build_integration_context
```

The web API, LLM orchestrator, and MCP server call the same application services rather than duplicating retrieval logic.

---

## 11. Retrieval Pipeline

```text
question
  -> normalization and intent/metadata extraction
  -> exact structured lookup
  -> dense retrieval + BM25 sparse retrieval
  -> payload filtering
  -> RRF fusion
  -> cross-encoder reranking
  -> relationship expansion
  -> diversity/deduplication
  -> context packing
```

### 11.1 Exact lookup first

When a query contains an endpoint, method, operation ID, schema, or exact error code, query PostgreSQL before vector search.

Examples:

- `POST /v1/customers`
- `customer_id`
- `payment_intent.succeeded`
- `401`
- `CreatePaymentIntent`

Exact results can seed or constrain hybrid retrieval.

### 11.2 Hybrid retrieval

Initial candidate generation:

- Dense retrieval: top 25
- Sparse BM25 retrieval: top 25
- RRF fusion: top 30
- Reranking: top 8-12
- Final packed evidence: typically 4-8 sources, depending on workflow

These values are configuration defaults and must be tuned through evaluation.

### 11.3 Mandatory filters

Every Qdrant query filters by:

- `workspace_id`
- `source_id` or approved source set
- Active `revision_id`
- `embedding_profile_version`

Optional filters include method, path, API version, entity type, language, tag, and status code.

### 11.4 Relationship expansion

After reranking, FetchAPI may deterministically add:

- Referenced request/response schemas
- Authentication scheme
- Related code example
- Parent guide section
- Adjacent section
- Error definition

Expansion is workflow-specific and has a token budget.

### 11.5 Context packing

Each evidence item receives a stable identifier:

```text
[S1], [S2], [S3], ...
```

The model receives:

- Source ID
- Entity type
- Version
- Method/path when applicable
- Title
- Content
- Source URL/pointer

No untrusted document content is placed in the system-instruction section.

---

## 12. Grounded Generation and Streaming

### 12.1 One generation call

The normal answer path uses **one streamed LLM call**.

The prompt requires the model to:

- Use only the supplied evidence for factual API claims
- Cite supported claims with allowed IDs such as `[S1]`
- State assumptions explicitly
- Distinguish documented facts from recommendations
- Say when evidence is missing
- Never cite an identifier that was not supplied

The server accumulates the streamed text, extracts cited IDs, rejects unknown IDs, maps valid IDs to authoritative citation metadata, and emits the final metadata event.

This avoids a second model call that could disagree with the streamed answer.

### 12.2 Stream event contract

For a `POST` streaming endpoint consumed with `fetch()` and Web Streams:

```text
event: start
data: { query_id, workflow }

event: token
data: { text }

event: evidence
data: { source_id, title, source_url, ... }   # optional early event

event: result
data: {
  cited_source_ids,
  support_status,
  warnings,
  validation,
  usage,
  latency_ms
}

event: error
data: { code, message, retryable }

event: done
data: {}
```

The frontend must not use the browser `EventSource` API for a POST endpoint; it should parse the streamed response from `fetch()`.

### 12.3 Support status

Do not present an uncalibrated model-generated number as "confidence."

Use:

```text
SUPPORTED
PARTIALLY_SUPPORTED
INSUFFICIENT_EVIDENCE
CONFLICTING_EVIDENCE
VALIDATION_FAILED
```

A numeric score may be added only after calibration against an evaluation dataset and must be labeled with its meaning.

### 12.4 Contradictions

Potential contradictions can be identified from:

- Conflicting canonical fields in the same active revision
- Duplicate documentation sections describing the same entity differently
- Explicit version differences
- Model-detected conflict supported by at least two cited sources

The UI labels model-detected cases as **possible documentation conflict** unless a deterministic comparison confirms the conflict.

---

## 13. Integration Generation and Validation

### 13.1 Generation context

For integration generation, retrieve or load deterministically:

- Operation
- Base URL/server
- Authentication scheme and scopes
- Required parameters and request body fields
- Request/response content types
- Relevant examples
- Error responses
- Pagination, retries, idempotency, and rate-limit guidance when documented

### 13.2 Output structure

Generated integrations should contain:

- Dependency/install command
- Environment variables and secret placeholders
- Authentication setup
- Request construction
- Response handling
- Documented error handling
- Pagination/retry handling when relevant
- Assumptions and unsupported details
- Citations

### 13.3 Validation stages

1. **API contract validation:** method, path, parameters, headers, body fields, content type, and version
2. **Schema validation:** request sample against the canonical OpenAPI/JSON Schema when available
3. **Syntax validation:** language parser, compiler front-end, formatter, or static analyzer
4. **Security review:** ensure no real credentials are inserted and logs do not expose secrets

Generated code must never be executed directly on the API host.

---

## 14. HTTP API Surface

Versioned routes:

```text
POST   /v1/sources/openapi/upload
POST   /v1/sources/openapi/url
GET    /v1/sources
GET    /v1/sources/{source_id}
DELETE /v1/sources/{source_id}
POST   /v1/sources/{source_id}/sync
GET    /v1/jobs/{job_id}
POST   /v1/jobs/{job_id}/cancel

GET    /v1/sources/{source_id}/operations
GET    /v1/operations/{operation_id}
GET    /v1/schemas/{schema_id}
GET    /v1/sources/{source_id}/schemas
GET    /v1/sources/{source_id}/auth

POST   /v1/query
POST   /v1/sources/{source_id}/search
POST   /v1/integrations/generate
POST   /v1/validate/request

GET    /health/live
GET    /health/ready
GET    /metrics
```

All request and response bodies use explicit Pydantic models. Error responses follow a stable problem-details-inspired shape.

---

## 15. MCP Server

Use the official MCP Python SDK and Streamable HTTP transport.

### 15.1 Tool design

Nine focused, structured tools:

```text
fetch_list_sources
fetch_search_docs
fetch_get_operation
fetch_get_schema
fetch_get_auth
fetch_generate_integration
fetch_validate_request
fetch_explain_error
fetch_compare_versions
```

### 15.2 MCP response requirements

- Return structured fields, not prose alone
- Include source IDs and URLs
- Include active API/documentation version
- Include support status
- Keep tool descriptions precise enough for reliable selection
- Reuse application services; do not call the public HTTP API from inside the same process
- Require authorization when exposed outside localhost

### 15.3 Resources

Future work may expose read-only MCP resources for:

- Source catalog
- Operation documents
- Schema documents
- Revision changelogs

---

## 16. Caching

### 16.1 Retrieval cache key

Include:

- Workspace
- Active revision IDs
- Normalized query
- Retrieval configuration version
- Embedding profile version
- Reranker version
- Filters

### 16.2 Answer cache key

Include everything above plus:

- Workflow
- Model provider and model ID
- Prompt version
- Generation settings
- Requested language/SDK

### 16.3 Invalidation

Activating or deleting a revision invalidates all source-dependent caches. Cache keys should normally make stale entries unreachable even before deletion.

Do not cache failed, interrupted, or insufficiently parsed streams as complete answers.

---

## 17. Security and Abuse Controls

### 17.1 Tenant isolation

- Every database query is scoped by workspace
- Every vector query includes workspace and active revision filters
- No user-provided payload filter is passed directly to Qdrant
- Authorization is checked in application services, not only HTTP controllers

### 17.2 Prompt injection

- Retrieved content is enclosed as untrusted evidence
- The system prompt explicitly forbids following instructions from documents
- Tool permissions are controlled by the orchestrator, not by document text
- Documents cannot request secrets, network access, or policy changes
- Generated answers cite evidence; unsupported actions are rejected

### 17.3 Secrets

- Never index credentials, cookies, or authorization headers
- Redact common secret patterns before persistence and logging
- Generated examples use environment-variable placeholders
- Provider keys remain server-side

### 17.4 Input limits

Enforce:

- File size limits
- YAML alias/expansion protection (capped at 100 per document)
- JSON nesting limits where practical
- Crawl budgets
- Query length limits
- Rate limits
- Model token budgets
- Worker time and memory limits

### 17.5 MCP authorization

Local development may use localhost-only access. Any remote MCP deployment must use supported authorization, TLS, origin validation, and per-workspace access checks.

---

## 18. Observability

### 18.1 Structured logs

Every request/job log includes:

- Correlation ID
- Workspace ID
- Source/revision ID when applicable
- Query/job ID
- Workflow and stage
- Duration
- Result count or status
- Error code

Never log document bodies, prompts, generated code, or secrets by default.

### 18.2 Traces

Use OpenTelemetry-compatible tracing for:

```text
HTTP request
  -> intent classification
  -> exact lookup
  -> dense retrieval
  -> sparse retrieval
  -> fusion
  -> reranking
  -> relationship expansion
  -> model generation
  -> citation verification
  -> persistence
```

### 18.3 Metrics

- Ingestion success/failure rate
- Ingestion duration by stage
- Pages and bytes fetched
- Chunk/entity counts
- Retrieval latency and candidate counts
- Reranker latency
- LLM latency, tokens, and estimated cost
- Cache hit rate
- Support-status distribution
- Citation validation failures
- Validation failure categories
- MCP tool call counts and failures

---

## 19. Testing and Evaluation

### 19.1 Test layers

1. **Unit tests:** parsers, normalizers, chunkers, filters, validators, cache keys
2. **Contract tests:** LLM adapter, embedding adapter, Qdrant repository, MCP tool schemas
3. **Integration tests:** PostgreSQL, Qdrant, Redis, object storage, worker
4. **API tests:** authentication, validation, errors, streaming event order
5. **End-to-end tests:** ingest fixture -> query -> citation -> validation
6. **Security tests:** SSRF, redirect bypass, cross-workspace access, prompt injection fixtures
7. **Evaluation tests:** retrieval and answer quality against curated datasets

### 19.2 Evaluation dataset

Versioned fixtures from Petstore (19 ops), Stripe (587 ops), and GitHub GHES (962 ops). 30 questions per dataset, 5 abstention questions per set.

Question categories:

- Exact endpoint lookup
- Parameter and schema questions
- Authentication
- Error codes
- Pagination
- Webhooks
- Code generation
- Request validation
- Ambiguous questions
- Unanswerable questions

### 19.3 Retrieval metrics

- Recall@5, Recall@10
- MRR
- Exact operation/schema retrieval rate
- Reranker lift over fused retrieval

Results (hybrid mode, 25 non-abstention questions per dataset):

| Dataset | Recall@5 | Recall@10 | MRR |
|---|---|---|---|
| Petstore | 1.00 | 1.00 | 0.96 |
| Stripe | 0.84 | 0.84 | 0.81 |
| GitHub GHES | 0.84 | 0.84 | 0.74 |

### 19.4 Answer metrics

- Claim support rate
- Citation precision and completeness
- Correct abstention rate
- Version correctness

Results (Petstore, 30 questions):

| Metric | Result | Target |
|---|---|---|
| Citation accuracy | 0.72 | >= 0.70 |
| Abstention accuracy | 0.87 | >= 0.85 |
| Groundedness | 0.72 | >= 0.70 |

### 19.5 Code and request metrics

- Correct method/path
- Required authentication included
- Required parameters/body fields included
- No invented fields
- Schema-valid request rate
- Syntax-valid code rate

---

## 20. Repository Structure

```text
fetchapi/
+-- backend/
|   +-- src/fetch/
|   |   +-- main.py
|   |   +-- config.py
|   |   +-- api/
|   |   |   +-- dependencies.py
|   |   |   +-- errors.py
|   |   |   +-- v1/
|   |   |       +-- sources.py
|   |   |       +-- operations.py
|   |   |       +-- queries.py
|   |   |       +-- jobs.py
|   |   |       +-- integrations.py
|   |   |       +-- validation.py
|   |   +-- application/
|   |   |   +-- sources/
|   |   |   +-- ingestion/
|   |   |   +-- retrieval/
|   |   |   +-- queries/
|   |   |   +-- integrations/
|   |   |   +-- validation/
|   |   +-- domain/
|   |   |   +-- entities.py
|   |   |   +-- enums.py
|   |   |   +-- errors.py
|   |   |   +-- protocols.py
|   |   +-- infrastructure/
|   |   |   +-- db/
|   |   |   +-- qdrant/
|   |   |   +-- redis/
|   |   |   +-- storage/
|   |   |   +-- openapi/
|   |   |   +-- embeddings/
|   |   |   +-- llm/
|   |   +-- mcp/
|   |   +-- config.py
|   +-- migrations/
|   +-- tests/
|       +-- unit/
|       +-- integration/
|       +-- security/
|       +-- fixtures/
+-- frontend/
|   +-- app/
|   +-- components/
|   +-- features/
|   +-- lib/
+-- evals/
|   +-- datasets/
|   +-- fixtures/
|   +-- runners/
|   +-- thresholds.json
+-- examples/
|   +-- petstore/
|   +-- github/
|   +-- stripe/
+-- infra/
|   +-- compose.yaml
+-- docs/
|   +-- assets/
+-- ARCHITECTURE.md
+-- CLAUDE.md
+-- README.md
+-- Makefile
+-- .env.example
```

### 20.1 Dependency direction

```text
API / MCP / Worker entrypoints
            |
            v
Application services
            |
            v
Domain models and protocols
            ^
            |
Infrastructure adapters
```

The domain layer must not import FastAPI, SQLAlchemy, Qdrant, Redis, or any LLM/MCP SDK.

---

## 21. Technology Choices

| Concern | Choice | Notes |
|---|---|---|
| Runtime | Python 3.12+ | Pin exact version in project tooling |
| HTTP API | FastAPI | Async I/O and typed API contracts |
| Relational store | PostgreSQL + SQLAlchemy 2 + Alembic | Authoritative metadata and canonical IR |
| Retrieval index | Qdrant | Dense/sparse retrieval and payload filtering |
| Background tasks | asyncio + PostgreSQL job state | Ingestion runs in-process; DB owns durable state |
| Cache/locks | Redis | Retrieval cache, answer cache, stampede locks |
| Object storage | S3-compatible API; MinIO locally | Immutable source snapshots |
| Dense embeddings | NVIDIA NIM (`nv-embedqa-e5-v5`, 1024-dim) | Versioned embedding profile; swappable via env vars |
| Sparse retrieval | Qdrant BM25 text index | Exact paths, parameters, codes, and identifiers |
| Reranker | NVIDIA NIM (`nv-rerankqa-mistral-4b-v3`) | httpx direct - NIM /ranking is not OpenAI-compatible |
| LLM | NVIDIA NIM default; any OpenAI-compatible endpoint | Model ID and provider set through env vars |
| OpenAPI validation | `openapi-spec-validator` | OpenAPI 3.0 and 3.1 |
| MCP | Official Python SDK | Streamable HTTP |
| Frontend | Next.js 15 + TypeScript | SSE streaming query UX |
| Observability | OpenTelemetry-compatible | Vendor-neutral core traces |
| Quality | Ruff, mypy, pytest | Enforced in CI |

---

## 22. Architectural Decisions

Decision entries are append-only. A decision may be marked **Superseded**, but it is not deleted.

### ADR-011 - Provider-independent LLM, embedding, and reranking interfaces

**Status:** Accepted
**Decision:** LLM generation, dense embedding, sparse embedding, and reranking are implemented behind typed protocol interfaces. No application or domain code imports provider-specific SDKs directly.
**Reasoning:** Provider availability and pricing change. Free-tier deployment (e.g., NVIDIA NIM) and paid deployment must be swappable through environment configuration without code changes.

### ADR-010 - Use support statuses instead of uncalibrated confidence percentages

**Status:** Accepted
**Decision:** Return evidence support states such as `SUPPORTED` and `INSUFFICIENT_EVIDENCE`. Add numeric confidence only after calibration.
**Reasoning:** Retrieval and model scores are not probabilities. A polished confidence bar can communicate false certainty.

### ADR-009 - Keep models and prompts configurable and versioned

**Status:** Accepted
**Decision:** Model IDs, embedding profiles, prompts, and retrieval parameters are configuration records, not architectural constants.
**Reasoning:** Providers and model versions change. Reproducible experiments require explicit version identifiers without hardcoding the whole architecture to one release.

### ADR-008 - Use asyncio background tasks for ingestion, not a separate worker process

**Status:** Accepted
**Decision:** Ingestion runs as `asyncio.create_task()` in the FastAPI process, backed by a persisted job state machine in PostgreSQL.
**Reasoning:** FetchAPI is a single-user self-hosted tool. A separate Celery worker and Redis broker add significant operational friction for local `docker compose up` use with no meaningful benefit at this scale. The ingestion service is fully decoupled from the execution mechanism - a future multi-tenant deployment can add a real task queue by changing one call site without touching domain or ingestion logic.

### ADR-007 - Use a bounded workflow, not unconstrained multi-agent loops

**Status:** Accepted
**Decision:** Implement typed workflows with explicit tools, limits, and deterministic validation.
**Reasoning:** Most tasks require orchestration, not multiple autonomous personas. Bounded workflows are easier to test, observe, and explain.

### ADR-006 - Stream one generated answer and map citations deterministically

**Status:** Accepted
**Supersedes:** Original two-model-call streaming/citation design
**Decision:** The model streams one answer containing approved source IDs. The server validates and maps those IDs to citation objects.
**Reasoning:** A second LLM call can produce citations inconsistent with the answer, while doubling cost and latency.

### ADR-005 - Use RRF as the initial dense/sparse fusion method

**Status:** Accepted
**Decision:** Fuse dense and BM25 candidate rankings with RRF, then rerank.
**Reasoning:** RRF is insensitive to incompatible score scales.

### ADR-004 - Use relationship-aware, structure-preserving chunks

**Status:** Accepted
**Supersedes:** "Always one fully flattened chunk per endpoint"
**Decision:** Keep required operation facts together, preserve schemas as canonical entities, and expand related schema/auth/example chunks after retrieval.
**Reasoning:** One endpoint chunk is excellent for many questions, but fully flattening large or recursive schemas produces oversized, duplicated, and hard-to-maintain chunks.

### ADR-003 - Use a shared Qdrant collection per index profile

**Status:** Accepted
**Supersedes:** One Qdrant collection per API
**Decision:** Store sources in a shared, versioned collection and isolate them with workspace/source/revision payload filters.
**Reasoning:** This avoids collection explosion, supports controlled cross-source search, and follows Qdrant's multitenancy guidance.

### ADR-002 - Use PostgreSQL as source of truth and Qdrant as a derived index

**Status:** Accepted
**Supersedes:** Qdrant-only persistence
**Decision:** PostgreSQL owns source metadata, revisions, canonical API entities, jobs, traces, and evaluations. Qdrant stores retrieval projections.
**Reasoning:** FetchAPI's actual product data is relational and versioned. Collection metadata and payload aggregation are not a durable substitute for source lifecycle, revisions, jobs, workspaces, evaluations, and auditability.

### ADR-001 - Build a canonical API documentation IR

**Status:** Accepted
**Decision:** Normalize source formats into operations, schemas, auth schemes, examples, errors, guides, and relations before indexing.
**Reasoning:** Request validation, version comparison, code generation, and exact lookup require structured facts that cannot reliably be reconstructed from text chunks.

---

## 23. Key Risks

| Risk | Mitigation |
|---|---|
| Large/recursive schemas exceed context limits | Canonical schema storage, bounded projections, relationship expansion |
| LLM generates plausible but undocumented code | Deterministic contract checks, citations, abstention, syntax/schema validation |
| Index and database drift | Revision activation gate and reconciliation jobs |
| Cross-tenant leakage | Mandatory workspace/revision filters and security tests |
| Retrieval changes silently reduce quality | Versioned evaluation datasets and CI thresholds |
| Dependency/model churn | Provider adapters, lockfiles, configuration versions |

---

## 24. Interview Narrative

The strongest technical story is not "I built a chatbot over API docs." It is:

> I built a version-aware API documentation intelligence layer. It normalizes OpenAPI specs into a canonical API model, indexes structure-preserving projections with hybrid dense and BM25 retrieval, reranks and expands related schemas, and uses a bounded workflow for Q&A, integration generation, request validation, error diagnosis, and version comparison. PostgreSQL remains the source of truth, Qdrant is a rebuildable retrieval index, citations are mapped deterministically, and quality is measured with retrieval, grounding, abstention, and code-validation evaluations. The same services are exposed through a web UI, FastAPI, and structured MCP tools.

---

## 25. Deployment Profiles

### Local

Used during development. All services run via Docker Compose.

- PostgreSQL, Qdrant, Redis, MinIO (Docker)
- FastAPI (Docker)
- Next.js (local dev server or Docker)
- LLM/embedding/reranker: configurable via env vars

### Free Portfolio Hosting

Minimal architectural changes - only provider and infrastructure swap.

- Frontend: Vercel Hobby
- FastAPI + MCP: Render or Railway free tier
- PostgreSQL: Neon free tier
- Qdrant: Qdrant Cloud free tier
- Redis: Upstash free tier
- Object storage: Cloudflare R2 free tier
- LLM + embeddings + reranker: NVIDIA NIM free API

Provider swap requires only environment variable changes. No domain or application code changes. Permitted by ADR-009 and ADR-011.

---

## 26. External Design References

- Qdrant multitenancy: <https://qdrant.tech/documentation/manage-data/multitenancy/>
- Qdrant hybrid queries: <https://qdrant.tech/documentation/search/hybrid-queries/>
- Qdrant text/BM25 search: <https://qdrant.tech/documentation/search/text-search/>
- MCP Python SDK: <https://py.sdk.modelcontextprotocol.io/>
- MCP transports: <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
- OpenAPI Specification: <https://spec.openapis.org/oas/latest.html>
- OpenAPI Spec Validator: <https://github.com/python-openapi/openapi-spec-validator>
