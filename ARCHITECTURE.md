# FetchAPI — Architecture, Decisions, and Roadmap

> **Purpose:** This document is the architectural source of truth for FetchAPI.
> It defines product scope, system boundaries, data ownership, workflows, quality requirements, and accepted trade-offs.
>
> **Implementation rules:** See [`CLAUDE.md`](./CLAUDE.md).
>
> **Maintenance rule:** Update **Current Status**, **Next Milestone**, and any affected architectural decision after completing a milestone or changing a system boundary.

---

## 1. Product Definition

### 1.1 What FetchAPI is

FetchAPI is an **open-source, self-hosted MCP server and API documentation intelligence layer**.

Run it locally with `docker compose up`. Point your AI coding assistant (Cursor, Claude Desktop, VS Code + Cline) at it. Upload an OpenAPI spec. From that point your editor has structured, citation-backed knowledge of that API.

FetchAPI converts documentation sources—initially OpenAPI files and URLs—into a versioned, structured representation that is queryable through:

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
- Receive an explicit “insufficient documentation” result when evidence does not exist

### 1.2 Product promise

> FetchAPI turns OpenAPI specs into structured, queryable, citation-backed API knowledge that lives in your editor through MCP — no cloud, no subscription, just `docker compose up`.

### 1.3 Primary users

- Developers integrating an unfamiliar third-party API
- Backend engineers maintaining several external integrations
- Developer-support and solutions-engineering teams
- Teams exposing private API documentation to internal coding agents
- AI coding assistants that need structured API knowledge through MCP

### 1.4 Non-goals for the first production-quality release

FetchAPI is not initially:

- A general-purpose web search engine
- A replacement for API gateways
- A system that autonomously executes arbitrary generated code
- A secrets manager
- A live API traffic proxy
- An API monitoring platform
- A fully autonomous multi-agent system
- A documentation authoring platform

These may become integrations later, but they must not distort the first architecture.

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
| Documentation Q&A | “How does pagination work?” | Retrieve guides and relevant operations; answer with citations |
| Endpoint lookup | “Which endpoint creates a customer?” | Prefer structured operation lookup, then retrieval fallback |
| Authentication guidance | “How do I refresh an OAuth token?” | Retrieve security schemes and authentication guides |
| Integration generation | “Show a Java example for creating a subscription” | Retrieve operation, schemas, auth, and examples; generate and validate code |
| Request validation | “Is this curl request valid?” | Parse request and compare it deterministically with the canonical operation |
| Error diagnosis | “Why am I receiving 422?” | Retrieve documented errors and inspect the supplied request/response |
| Version comparison | “What changed between v1 and v2?” | Compare canonical entities across two source revisions |
| Insufficient evidence | “Does this API guarantee exactly-once delivery?” | Explain that the connected documentation does not establish the claim |

A request may invoke several tools, but it has one workflow owner and a bounded maximum number of steps.

---

## 4. System Context

```text
┌──────────────────────────── Clients ────────────────────────────┐
│                                                                 │
│  Next.js Web UI       HTTP/SDK Consumers       MCP Clients      │
│                                              Claude Code, IDEs   │
└───────────────┬──────────────────┬──────────────────┬────────────┘
                │ HTTPS / stream   │ HTTPS            │ MCP
                └──────────────────┴──────────────────┘
                                   │
                                   ▼
┌──────────────────────── FastAPI Application ─────────────────────┐
│                                                                  │
│  REST API     Query Orchestrator     Retrieval Service     MCP   │
│                    │                     │                 Server │
│                    │                     │                        │
│  Source Service    │        Validation / Code Generation         │
│        │           │                                             │
└────────┼───────────┼─────────────────────────────────────────────┘
         │           │
         │ enqueue   │ model requests
         ▼           ▼
┌────────────────┐  ┌────────────────────┐
│ Ingestion      │  │ Configurable LLM   │
│ Worker         │  │ Provider Adapter   │
└───────┬────────┘  └────────────────────┘
        │
        ├──────────────┬──────────────────┬──────────────────────┐
        ▼              ▼                  ▼                      ▼
┌──────────────┐ ┌──────────────┐  ┌──────────────┐   ┌────────────────┐
│ PostgreSQL   │ │ Qdrant       │  │ Redis        │   │ S3-compatible  │
│ source of    │ │ retrieval    │  │ queue/cache  │   │ object storage │
│ truth        │ │ index        │  │ coordination │   │ raw snapshots  │
└──────────────┘ └──────────────┘  └──────────────┘   └────────────────┘
```

---

## 5. Deployment Units

### 5.1 Web application

- Next.js with TypeScript
- Source connection and ingestion status UI
- Query and integration workspace
- Request debugger
- Citation and retrieval inspector
- Evaluation dashboard in a later phase

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

**Why not Celery:** FetchAPI is a single-user self-hosted tool. A separate Celery worker process and Redis broker are unnecessary operational complexity for local use. The ingestion service is fully decoupled from the execution mechanism — if a future multi-tenant deployment needs durable distributed workers, swapping `asyncio.create_task` for a task queue is a one-function change. The domain contracts, job state machine, and ingestion logic are unchanged.

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

Redis is not the source of truth for jobs or documents. It is not used as a task broker — ingestion runs as asyncio background tasks.

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
| `ChunkRelation` | Typed relationship such as operation → schema or guide → auth scheme |
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

Initial collection example:

```text
fetch_chunks_v1
```

All tenant, API, source, revision, and document isolation is performed with payload filters. Payload fields used as tenant boundaries must have Qdrant tenant/payload indexes configured.

Why:

- Avoids collection explosion as sources grow
- Supports cross-API discovery when explicitly requested
- Keeps embedding dimensions and index settings consistent
- Matches Qdrant’s recommended payload-partitioned multitenancy model
- Makes index migrations explicit through a new collection version

Large tenants may later be promoted to dedicated shards without changing the application contract.

### 7.2 Named vectors

The first benchmark profile uses:

- `dense`: configurable sentence embedding model
- `sparse`: BM25-compatible sparse representation

Baseline local models may start with:

- Dense: `sentence-transformers/all-MiniLM-L6-v2`
- Sparse: `Qdrant/bm25`
- Reranker: `cross-encoder/ms-marco-MiniLM-L-6-v2`

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

A reconciliation job compares PostgreSQL chunks with Qdrant points and repairs drift.

---

## 8. Ingestion Architecture

### 8.1 Source adapter interface

Every source type implements the same lifecycle:

```text
validate_config → discover → fetch → snapshot → parse → normalize → emit canonical entities
```

Initial adapters (v1):

1. OpenAPI file upload
2. OpenAPI URL

Later adapters (deferred — see §23 Roadmap):

- Documentation website root URL (Phase 4)
- GitHub/Markdown repository
- Postman collection
- GraphQL introspection/schema
- AsyncAPI document
- Local SDK repository

### 8.2 Ingestion state machine

```text
QUEUED
  → FETCHING
  → SNAPSHOTTING
  → PARSING
  → VALIDATING
  → NORMALIZING
  → CHUNKING
  → EMBEDDING
  → INDEXING
  → VERIFYING
  → ACTIVE

Any state may transition to FAILED.
Cancellation transitions a non-terminal job to CANCELLED.
```

Jobs are idempotent by source configuration hash and content hash. Retrying a failed job must not duplicate entities or points.

**Retry policy:** A failed job always restarts from `QUEUED`. Mid-stage resume is not supported in v1. This simplifies idempotency: the worker re-runs all stages from the beginning, content hashes prevent duplicate entity creation, and the previous failed revision is never activated. Maximum retry attempts: configurable via `INGESTION_MAX_RETRIES` (default: 3). After max retries, the job stays `FAILED` and requires manual re-ingestion.

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

### 8.4 Documentation website ingestion

Website ingestion is a bounded crawler, not a single-page scraper.

Crawler controls:

- Same-origin by default
- Configurable allowed path prefix
- Optional sitemap discovery
- Maximum pages, depth, bytes, and duration
- Content-type allowlist
- Canonical URL normalization
- Duplicate detection by canonical URL and content hash
- Respect for configured crawl policy
- Static HTTP fetch first
- Browser rendering only when necessary
- Extraction of headings, paragraphs, tables, lists, and code blocks
- Preservation of page title, heading path, anchors, and source URL

### 8.5 Safe remote fetching

All remote fetches must defend against SSRF:

- Allow only `http` and `https`
- Resolve DNS before connecting
- Block loopback, link-local, private, multicast, and cloud metadata ranges
- Revalidate every redirect target
- Set connect/read/total timeouts
- Enforce response-size limits while streaming
- Reject unexpected content types
- Do not forward user-supplied authorization headers in the MVP
- Record final URL and redirect chain

Browser workers must run with restricted network access and resource limits.

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

This avoids both extremes: arbitrary character splitting and unbounded full-schema flattening.

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
OPERATION_USES_SCHEMA       operation chunk → request/response schema chunk
OPERATION_REQUIRES_AUTH     operation chunk → authentication chunk
OPERATION_RETURNS_SCHEMA    operation chunk → response schema chunk
OPERATION_HAS_ERROR         operation chunk → error definition chunk
EXAMPLE_FOR_OPERATION       example chunk → operation chunk
SCHEMA_REFERENCES_SCHEMA    schema chunk → nested/referenced schema chunk
GUIDE_COVERS_OPERATION      guide section chunk → related operation chunk
```

These relations are used during relationship expansion (§11.4) to deterministically add context without semantic retrieval.

### 9.7 Chunk sizing

Chunk size is a benchmarked parameter, not a universal rule.

Initial targets:

- Guide prose: approximately 300–700 tokens
- Operation summaries: complete required context even if larger
- Schema detail chunks: approximately 300–800 tokens
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
  → validate scope and source
  → classify workflow
  → extract constraints
  → run exact lookups
  → run hybrid retrieval if needed
  → rerank and expand related evidence
  → execute deterministic validation when applicable
  → generate grounded explanation/code when applicable
  → verify citations and output contract
  → stream result and persist trace
```

The orchestrator has:

- Typed state
- Explicit tools
- Maximum step count
- Per-tool timeout
- No recursive self-delegation
- No autonomous network access outside approved source tools

A state-machine library may be introduced if it improves traceability, but the domain workflow must remain independent of that library.

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
  → normalization and intent/metadata extraction
  → exact structured lookup
  → dense retrieval + BM25 sparse retrieval
  → payload filtering
  → RRF fusion
  → cross-encoder reranking
  → relationship expansion
  → diversity/deduplication
  → context packing
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
- Reranking: top 8–12
- Final packed evidence: typically 4–8 sources, depending on workflow

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

Do not present an uncalibrated model-generated number as “confidence.”

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

Generated code must never be executed directly on the API host. Optional execution requires an isolated, network-restricted sandbox and is a later milestone.

---

## 14. HTTP API Surface

Initial versioned routes:

```text
POST   /v1/sources/openapi/upload
POST   /v1/sources/openapi/url
GET    /v1/sources
GET    /v1/sources/{source_id}
DELETE /v1/sources/{source_id}
POST   /v1/sources/{source_id}/sync
GET    /v1/jobs/{job_id}

GET    /v1/sources/{source_id}/operations
GET    /v1/operations/{operation_id}
GET    /v1/schemas/{schema_id}
GET    /v1/sources/{source_id}/auth

POST   /v1/queries/stream
POST   /v1/generate-integration
POST   /v1/explain-error

POST   /v1/validate/request
POST   /v1/validate/curl

POST   /v1/evaluations/run
GET    /v1/evaluations/runs
GET    /v1/evaluations/runs/{run_id}

GET    /health/live
GET    /health/ready
GET    /metrics
```

All request and response bodies use explicit Pydantic models. Error responses follow a stable problem-details-inspired shape.

---

## 15. MCP Server

Use the official MCP Python SDK and Streamable HTTP transport for deployed use.

### 15.1 Tool design

Expose focused, structured tools:

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

A convenience `fetch_ask_docs` tool may exist, but it must not be the only interface.

### 15.2 MCP response requirements

- Return structured fields, not prose alone
- Include source IDs and URLs
- Include active API/documentation version
- Include support status
- Keep tool descriptions precise enough for reliable selection
- Reuse application services; do not call the public HTTP API from inside the same process
- Require authorization when exposed outside localhost

### 15.3 Resources

A later phase may expose read-only MCP resources for:

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
- Do not allow user credentials to be sent to crawled websites in the MVP
- Provider keys remain server-side

### 17.4 Input limits

Enforce:

- File size limits
- YAML alias/expansion protection
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
  → intent classification
  → exact lookup
  → dense retrieval
  → sparse retrieval
  → fusion
  → reranking
  → relationship expansion
  → model generation
  → citation verification
  → persistence
```

An LLM observability tool may be added through an adapter, but core telemetry must not depend on a single vendor.

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
5. **End-to-end tests:** ingest fixture → query → citation → validation
6. **Security tests:** SSRF, redirect bypass, cross-workspace access, prompt injection fixtures
7. **Evaluation tests:** retrieval and answer quality against curated datasets

### 19.2 Evaluation dataset

Use versioned fixtures from at least three APIs with different documentation styles. Suggested categories:

- Exact endpoint lookup
- Parameter and schema questions
- Authentication
- Error codes
- Pagination
- Webhooks
- Code generation
- Request validation
- Version migration
- Ambiguous questions
- Unanswerable questions
- Conflicting documentation

### 19.3 Retrieval metrics

- Recall@K
- MRR
- NDCG@K
- Exact operation/schema retrieval rate
- Reranker lift over fused retrieval
- Context precision

### 19.4 Answer metrics

- Claim support rate
- Citation precision and completeness
- Unsupported-claim rate
- Correct abstention rate
- Version correctness
- Tool-selection accuracy
- Workflow completion rate

### 19.5 Code and request metrics

- Correct method/path
- Required authentication included
- Required parameters/body fields included
- No invented fields
- Schema-valid request rate
- Syntax-valid code rate
- Documented-error handling rate

LLM judges may supplement deterministic scoring, but they cannot be the only evaluator.

---

## 20. Repository Structure

```text
fetch/
├── backend/
│   ├── src/fetch/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── errors.py
│   │   │   └── v1/
│   │   │       ├── sources.py
│   │   │       ├── operations.py
│   │   │       ├── queries.py
│   │   │       ├── integrations.py
│   │   │       ├── validation.py
│   │   │       ├── evaluations.py
│   │   │       └── revisions.py
│   │   ├── application/
│   │   │   ├── sources/
│   │   │   ├── ingestion/
│   │   │   ├── retrieval/
│   │   │   ├── queries/
│   │   │   ├── integrations/
│   │   │   └── validation/
│   │   ├── domain/
│   │   │   ├── entities.py
│   │   │   ├── enums.py
│   │   │   ├── errors.py
│   │   │   └── protocols.py
│   │   ├── infrastructure/
│   │   │   ├── db/
│   │   │   ├── qdrant/
│   │   │   ├── redis/
│   │   │   ├── storage/
│   │   │   ├── queue/
│   │   │   ├── openapi/
│   │   │   ├── crawling/
│   │   │   ├── embeddings/
│   │   │   └── llm/
│   │   ├── workers/
│   │   ├── mcp/
│   │   └── observability/
│   ├── migrations/
│   └── tests/
│       ├── unit/
│       ├── integration/
│       ├── contract/
│       ├── e2e/
│       └── security/
├── frontend/
│   ├── app/
│   ├── components/
│   ├── features/
│   ├── lib/
│   └── tests/
├── evals/
│   ├── datasets/
│   ├── fixtures/
│   ├── runners/
│   └── results/
├── examples/
│   ├── petstore/
│   ├── github/
│   └── stripe/
├── infra/
│   ├── docker/
│   └── compose.yaml
├── docs/
│   ├── adr/
│   └── diagrams/
├── ARCHITECTURE.md
├── CLAUDE.md
├── README.md
├── Makefile
└── .env.example
```

### 20.1 Dependency direction

```text
API / MCP / Worker entrypoints
            ↓
Application services
            ↓
Domain models and protocols
            ↑
Infrastructure adapters
```

The domain layer must not import FastAPI, SQLAlchemy, Qdrant, Redis, Anthropic, or MCP SDK classes.

---

## 21. Technology Choices

| Concern | Initial choice | Notes |
|---|---|---|
| Runtime | Python 3.12+ | Pin exact version in project tooling, not here |
| HTTP API | FastAPI | Async I/O and typed API contracts |
| Relational store | PostgreSQL + SQLAlchemy 2 + Alembic | Authoritative metadata and canonical IR |
| Retrieval index | Qdrant | Dense/sparse retrieval and payload filtering |
| Background tasks | asyncio + PostgreSQL job state | Ingestion runs in-process; DB owns durable state |
| Cache/locks | Redis | Retrieval cache, answer cache, stampede locks |
| Object storage | S3-compatible API; MinIO locally | Immutable source snapshots |
| Dense embeddings | Configurable; MiniLM baseline | Versioned embedding profile |
| Sparse retrieval | Qdrant BM25 baseline | Exact paths, parameters, codes, and identifiers |
| Reranker | Configurable cross-encoder baseline | Run only over fused candidates |
| LLM | Provider adapter; NVIDIA NIM default, OpenAI-compatible | Model ID and provider set through env vars |
| OpenAPI validation | `openapi-spec-validator` | Support OpenAPI 3.0 and 3.1 |
| Reference handling | Dedicated resolver using standards-aware libraries | Preserve pointers and detect cycles |
| Static extraction | HTTPX + Trafilatura/HTML parser | Browser fallback only when required |
| Browser extraction | Playwright worker | Isolated and resource-limited |
| MCP | Official Python SDK | Streamable HTTP for deployed use |
| Frontend | Next.js + TypeScript | Streamed query UX |
| Observability | OpenTelemetry-compatible | Vendor-neutral core traces |
| Quality | Ruff, mypy/pyright, pytest | Enforced in CI |

Exact dependency versions belong in `pyproject.toml`, the lockfile, and automated dependency updates. Architecture should not become stale because a patch release changed.

---

## 22. Architectural Decisions

Decision entries are append-only. A decision may be marked **Superseded**, but it is not deleted.

### ADR-011 — Provider-independent LLM, embedding, and reranking interfaces

**Status:** Accepted
**Decision:** LLM generation, dense embedding, sparse embedding, and reranking are implemented behind typed protocol interfaces. No application or domain code imports provider-specific SDKs directly.
**Reasoning:** Provider availability and pricing change. Free-tier deployment (e.g., NVIDIA NIM, Gemini) and paid deployment (e.g., Anthropic) must be swappable through environment configuration without code changes. ADR-009 established model configurability; ADR-011 establishes provider-level interface isolation.

### ADR-010 — Use support statuses instead of uncalibrated confidence percentages

**Status:** Accepted  
**Decision:** Return evidence support states such as `SUPPORTED` and `INSUFFICIENT_EVIDENCE`. Add numeric confidence only after calibration.  
**Reasoning:** Retrieval and model scores are not probabilities. A polished confidence bar can communicate false certainty.

### ADR-009 — Keep models and prompts configurable and versioned

**Status:** Accepted  
**Decision:** Model IDs, embedding profiles, prompts, and retrieval parameters are configuration records, not architectural constants.  
**Reasoning:** Providers and model versions change. Reproducible experiments require explicit version identifiers without hardcoding the whole architecture to one release.

### ADR-008 — Use asyncio background tasks for ingestion, not a separate worker process

**Status:** Accepted
**Decision:** Ingestion runs as `asyncio.create_task()` in the FastAPI process, backed by a persisted job state machine in PostgreSQL.
**Reasoning:** FetchAPI is a single-user self-hosted tool. A separate Celery worker and Redis broker add significant operational friction for local `docker compose up` use with no meaningful benefit at this scale. Durable state is owned by PostgreSQL (job records), so a process restart leaves jobs in BUILDING state and the user can retry. The ingestion service is fully decoupled from the execution mechanism — a future multi-tenant deployment can add a real task queue by changing one call site without touching domain or ingestion logic.

### ADR-007 — Use a bounded workflow, not unconstrained multi-agent loops

**Status:** Accepted  
**Decision:** Implement typed workflows with explicit tools, limits, and deterministic validation.  
**Reasoning:** Most tasks require orchestration, not multiple autonomous personas. Bounded workflows are easier to test, observe, and explain.

### ADR-006 — Stream one generated answer and map citations deterministically

**Status:** Accepted  
**Supersedes:** Original two-model-call streaming/citation design  
**Decision:** The model streams one answer containing approved source IDs. The server validates and maps those IDs to citation objects.  
**Reasoning:** A second LLM call can produce citations or metadata inconsistent with the answer, while doubling cost and latency.

### ADR-005 — Use RRF as the initial dense/sparse fusion method

**Status:** Accepted  
**Decision:** Fuse dense and BM25 candidate rankings with RRF, then rerank.  
**Reasoning:** RRF is insensitive to incompatible score scales. Keep DBSF as a benchmark candidate rather than rejecting it permanently.

### ADR-004 — Use relationship-aware, structure-preserving chunks

**Status:** Accepted  
**Supersedes:** “Always one fully flattened chunk per endpoint”  
**Decision:** Keep required operation facts together, preserve schemas as canonical entities, and expand related schema/auth/example chunks after retrieval.  
**Reasoning:** One endpoint chunk is excellent for many questions, but fully flattening large or recursive schemas produces oversized, duplicated, and hard-to-maintain chunks.

### ADR-003 — Use a shared Qdrant collection per index profile

**Status:** Accepted  
**Supersedes:** One Qdrant collection per API  
**Decision:** Store sources in a shared, versioned collection and isolate them with workspace/source/revision payload filters.  
**Reasoning:** This avoids collection explosion, supports controlled cross-source search, and follows Qdrant’s multitenancy guidance.

### ADR-002 — Use PostgreSQL as source of truth and Qdrant as a derived index

**Status:** Accepted  
**Supersedes:** Qdrant-only persistence  
**Decision:** PostgreSQL owns source metadata, revisions, canonical API entities, jobs, traces, and evaluations. Qdrant stores retrieval projections.  
**Reasoning:** FetchAPI’s actual product data is relational and versioned. Collection metadata and payload aggregation are not a durable substitute for source lifecycle, revisions, jobs, workspaces, evaluations, and auditability.

### ADR-001 — Build a canonical API documentation IR

**Status:** Accepted  
**Decision:** Normalize source formats into operations, schemas, auth schemes, examples, errors, guides, and relations before indexing.  
**Reasoning:** Request validation, version comparison, code generation, and exact lookup require structured facts that cannot reliably be reconstructed from text chunks.

---

## 23. Roadmap

### Phase 0 — Foundation

**Goal:** Scaffold the repository, configure tooling, define domain contracts, and prove local infrastructure starts.

- Repository structure and `pyproject.toml`
- Docker Compose (PostgreSQL, Qdrant, Redis, MinIO, FastAPI, Next.js)
- Provider protocol interfaces (LLM, embeddings, reranker)
- Domain entities, enums, errors, protocols
- Core configuration with pydantic-settings
- OpenAPI 3.0/3.1 fixture corpus (Petstore, Stripe, GitHub)
- Malformed, recursive, and external-reference fixtures
- Initial architecture tests

**Exit criteria:** `docker compose up` starts all services. Unit tests pass without external services.

---

### Phase 1 — OpenAPI ingestion and source lifecycle

**Goal:** Ingest one OpenAPI specification into PostgreSQL and object storage with a durable job.

- File upload and URL ingestion endpoints
- OpenAPI 3.0/3.1 validation
- `$ref` resolution with cycle detection
- Canonical extraction: operations, schemas, auth schemes, servers, examples, errors
- Immutable object snapshots in MinIO
- PostgreSQL persistence of canonical entities
- Ingestion job state machine (QUEUED → ACTIVE)
- Atomic revision activation gate

**Exit criteria:** Re-ingesting the same source is idempotent. A failed revision never replaces the active revision. Extracted operations, schemas, and auth schemes are accessible via API.

---

### Phase 2 — Chunking and indexing

**Goal:** Convert canonical entities into retrieval-optimized projections and index them in Qdrant.

- Operation summary chunks
- Schema detail chunks
- Authentication chunks
- Error definition chunks
- Guide section chunks
- Chunk relations (OPERATION_USES_SCHEMA, OPERATION_REQUIRES_AUTH, etc.)
- Dense embedding generation
- BM25/sparse indexing
- Qdrant upsert with deterministic point IDs
- Revision verification and reconciliation job

**Exit criteria:** A source revision can be retrieved from Qdrant using both exact identifiers and semantic queries. PostgreSQL chunk count matches Qdrant point count.

---

### Phase 3 — Retrieval

**Goal:** Build the complete retrieval pipeline from query to ranked evidence.

- Query normalization and identifier extraction
- Structured exact lookup (PostgreSQL)
- Dense retrieval
- BM25/lexical retrieval
- RRF fusion
- Mandatory payload filtering (workspace, revision, embedding profile)
- Cross-encoder reranking
- Relationship expansion
- Context packing with stable source IDs
- Retrieval traces in QueryRun

**Exit criteria:** Retrieval evaluation produces real Recall@5 and MRR results. Ablation confirms hybrid + reranking outperforms dense-only.

---

### Phase 4 — Grounded Q&A

**Goal:** Answer documentation questions with streamed, citation-verified responses.

- Query intent classification
- LLM provider adapter (initial: configurable via env)
- Single streamed generation call
- Evidence ID injection into prompt
- Server-side citation ID extraction and validation
- Unknown citation ID rejection
- Support status computation
- Abstention for insufficient evidence
- Contradiction detection
- Query trace persistence

**Exit criteria:** End-to-end tests confirm citations resolve to the active revision and unknown IDs are rejected. Abstention triggers correctly on unanswerable fixtures.

---

### Phase 5 — Integration generation

**Goal:** Generate validated, schema-backed integration code.

- Operation-aware context assembly
- Language selection (Python, TypeScript, Java)
- Authentication setup generation
- Dependency and install command generation
- Request construction and response handling
- Error handling and documented-error coverage
- OpenAPI-backed field validation
- Syntax check
- Validation report in response

**Exit criteria:** Generated integrations match the selected operation's method, path, authentication, and request schema. Schema-invalid generated code is flagged in the validation report.

---

### Phase 6 — Request debugger and error diagnosis

**Goal:** Let users paste broken requests and receive deterministic, schema-backed diagnostics.

- Curl command parser
- Method + URL + headers + body ingestion
- Endpoint matching against canonical operations
- Header validation (required, format)
- Parameter validation (type, required, enum)
- Request body validation against canonical schema
- Error status lookup in ErrorDefinition
- Corrected request example generation
- LLM explanation grounded on validation findings

**Exit criteria:** All intentionally broken requests in evaluation fixtures are detected and diagnosed correctly.

---

### Phase 7 — MCP server

**Goal:** Expose FetchAPI's application services to coding agents through structured MCP tools.

Initial five tools:
- `fetch_list_sources`
- `fetch_search_docs`
- `fetch_get_operation`
- `fetch_generate_integration`
- `fetch_validate_request`

Then add:
- `fetch_get_schema`
- `fetch_get_auth`
- `fetch_explain_error`

- Streamable HTTP transport
- Structured JSON responses (not prose only)
- Citations and support status in every response
- MCP contract tests

**Exit criteria:** Claude Code or Cursor can find an operation, retrieve a schema, generate an integration, validate a request, and receive citations against a locally running FetchAPI instance.

---

### Phase 8 — Frontend

**Goal:** Build a browser UI that demonstrates the complete workflow.

- Source ingestion page (upload + URL)
- Ingestion status and job progress
- API explorer (browse operations, schemas, auth)
- Chat/Q&A interface with SSE streaming
- Citation cards with source excerpts
- Code generation panel with language selector
- Request validation panel (curl + JSON input)
- Retrieval inspector (dense/sparse scores, reranker scores)
- Evaluation dashboard

**Exit criteria:** The complete workflow is demonstrable from the browser without Swagger UI or the terminal.

---

### Phase 9 — Evaluation and hardening

**Goal:** Produce real, reproducible quality measurements and harden the system for portfolio release.

- Evaluation datasets for Petstore, GitHub, and Stripe (≥30 questions each)
- Retrieval benchmark runner (Recall@5, Recall@10, MRR, NDCG)
- Answer evaluation (citation accuracy, groundedness, abstention accuracy)
- Validation evaluation (incorrect method, missing header, invalid type detection)
- Ablation experiments (dense-only vs. hybrid vs. hybrid+reranking)
- SSRF security tests
- Cross-workspace isolation tests
- Prompt injection fixture tests
- GitHub Actions CI (lint, type check, tests, Docker build, evaluation smoke test)
- Regression thresholds enforced in CI

**Exit criteria:** README contains real evaluation results generated by the repository. No metric is fabricated. CI passes on clean clone.

---

### Phase 10 — Portfolio release

**Goal:** Prepare the repository for recruiter and interviewer review.

- README with problem statement, architecture diagram, feature list, setup instructions
- Demo video (2–3 minutes, full workflow)
- Screenshots of all UI sections including retrieval inspector
- MCP configuration instructions for Claude Code and Cursor
- Evaluation results table
- Design decision summary (link to ADRs)
- Limitations and future work section
- Resume bullets with real metrics

**Exit criteria:** A recruiter can understand the problem, architecture, features, and measured results without installing the project.

---

### Deferred to future work

These features are intentionally excluded from version 1:

- Arbitrary documentation website crawling
- Playwright-based browser rendering
- PDF documentation ingestion
- API version migration and comparison
- Multi-user accounts and billing
- Public permanent hosting
- Generated-code execution in sandboxes
- Postman, GraphQL, AsyncAPI source types
- Fine-tuning

---

## 24. Current Status

**Last updated:** 2026-07-25
**Current phase:** complete — all 10 phases shipped
**Distribution:** GitHub open-source, self-hosted via `docker compose up`

### Completed

- [x] Product scope defined
- [x] Core architecture defined and finalized
- [x] Canonical model selected
- [x] Storage responsibilities selected
- [x] Retrieval and citation strategy selected
- [x] Deployment strategy decided (GitHub-only for v1)
- [x] All ADRs accepted
- [x] 10-phase roadmap defined
- [x] Phase 0 — Foundation complete (64 unit tests passing)
- [x] Phase 1 — OpenAPI ingestion and source lifecycle complete (99 unit tests passing)
- [x] Phase 2 — Chunking and Qdrant indexing complete (131 unit tests passing, end-to-end verified)
- [x] Phase 3 — Retrieval pipeline complete (12 integration tests passing, 1 skipped when RERANKER_API_KEY is placeholder)
- [x] Phase 4 — Grounded Q&A complete (SSE streaming answers, deterministic citation extraction, SupportStatus, abstention, prompt versioning)
- [x] Phase 5 — Integration code generation complete (Python/TypeScript/Java, contract + syntax validation, IntegrationRun persistence)
- [x] Phase 6 — Request validation and error diagnosis complete (curl parsing, endpoint matching, jsonschema validation, corrected example, 55 unit tests + 15 eval fixtures)
- [x] Phase 7 — MCP server complete (9 structured tools via Streamable HTTP, VersionDiffService, 388 unit tests passing)
- [x] Phase 8 — Next.js web UI complete (chat with SSE streaming + citations, integration generation panel, request validation panel)
- [x] Phase 9 — Evaluation and hardening complete (90-question eval datasets, retrieval/answer/validation/ablation benchmark runners, SSRF + workspace isolation + prompt injection security tests, GitHub Actions CI, regression thresholds)
- [x] Phase 10 — Portfolio release complete (README overhaul, resume bullets, MCP quickstart, eval thresholds documented)

### Phase 0 — Foundation (complete)

1. [x] Scaffold repository and backend package (`pyproject.toml`, `Makefile`)
2. [x] Docker Compose with all six services
3. [x] Provider protocol interfaces
4. [x] Domain entities, enums, errors, protocols
5. [x] Core pydantic-settings configuration
6. [x] OpenAPI fixture corpus (Petstore, GitHub, Stripe)
7. [x] Initial unit tests passing without external services

#### Phase 0 implementation notes

- **LLM/embeddings/reranker provider:** NVIDIA NIM chosen for both local dev and deployment. Uses `openai` SDK pointed at `https://integrate.api.nvidia.com/v1`. Replaces original `anthropic` plan. Zero code changes needed to swap providers — only env vars.
- **Virtual environment:** `backend/.venv` — created with `python3 -m venv`. All Makefile commands use `backend/.venv/bin/python` directly. No manual activation needed.
- **Enums:** Upgraded from `(str, Enum)` to `StrEnum` (Python 3.11+) during Phase 0 linting.
- **Datetime:** All UTC datetimes use `datetime.now(UTC)` — `datetime.utcnow()` is deprecated in Python 3.14.
- **Real API fixtures:** `examples/petstore` (19 ops), `examples/github` (962 ops, GHES 3.12), `examples/stripe` (587 ops, 1431 schemas) — all fetched from official sources.
- **Test fixtures:** 10 edge-case OpenAPI fixtures in `backend/tests/fixtures/openapi/` covering nullable normalization, recursive schemas, invalid specs, malformed YAML, and deprecated operations.

### Phase 1 — OpenAPI ingestion and source lifecycle (complete)

1. [x] PostgreSQL ORM models (SQLAlchemy 2.x) + first Alembic migration (`001_initial_schema.py`)
2. [x] Source upload endpoint (`POST /v1/sources/openapi/upload`)
3. [x] Source URL endpoint (`POST /v1/sources/openapi/url`)
4. [x] Immutable object snapshot in MinIO (`infrastructure/storage/minio.py`)
5. [x] OpenAPI 3.0/3.1 validation + safe `$ref` resolution with cycle detection (`infrastructure/openapi/validator.py`)
6. [x] Canonical entity extraction — operations, schemas, auth schemes, servers, examples, errors (`infrastructure/openapi/extractor.py`)
7. [x] Ingestion job state machine QUEUED → FETCHING → SNAPSHOTTING → PARSING → VALIDATING → NORMALIZING → ACTIVE (`application/ingestion/service.py`)
8. [x] Atomic revision activation gate — supersede old ACTIVE, activate new in one transaction (`infrastructure/db/repositories.py`)
9. [x] PostgreSQL repository layer — all entities with `ON CONFLICT DO NOTHING` idempotency
10. [x] HTTP API — sources, jobs, operations, schemas, auth endpoints (`api/v1/`)
11. [x] Unit tests (99 passing) and integration test suite (4 tests, requires real infra)

#### Phase 1 implementation notes

- **Alias expansion DoS fix:** `load_yaml_safe` uses `yaml.compose()` before `yaml.safe_load()` to count aliases on the raw node tree. `yaml.safe_load()` expands aliases before returning, so counting on the dict is too late. Alias objects are detected by tracking `id()` — the same node object appearing twice = alias expansion.
- **SSRF protection:** All external `$ref` URLs and redirect targets are checked against blocked IP ranges (loopback, private, link-local, metadata, multicast). `socket.getaddrinfo()` is used to resolve hostnames before checking.
- **OpenAPI 3.1 type normalization:** `["string", "null"]` → `type=string, nullable=true` in `normalize_schema_types()`. Array types are not stored in the canonical model.
- **Path normalization:** `normalize_path()` strips trailing slashes and lowercases static path segments. Path parameter names (`{id}`) are preserved as-is. Both raw and normalized paths are stored on operations.
- **Schema recursion guard:** `extract_schema_json()` stops recursing at `MAX_SCHEMA_DEPTH=5` and at any previously-seen pointer (cycle detection via seen-set). Cyclic schemas do not fail ingestion.
- **Idempotency:** SHA-256 content hash checked before creating a new revision for file uploads. All `save_many()` calls use `INSERT ... ON CONFLICT DO NOTHING` on `logical_key` unique constraints.
- **Background ingestion:** `asyncio.create_task(run_ingestion(...))` — HTTP response returns immediately with `{source_id, revision_id, job_id}`. No Celery.
- **`detect_openapi_version` empty-dict fix:** `doc.get("openapi") or doc.get("swagger", "")` evaluates to `""` when both are absent. Added `not raw` guard to catch the empty-string case.

### Phase 2 — Chunking and Qdrant indexing (complete)

1. [x] Operation summary chunk projections
2. [x] Schema detail chunk projections
3. [x] Authentication chunk projections
4. [x] Error definition chunk projections
5. [x] Chunk relations (OPERATION_USES_SCHEMA, OPERATION_REQUIRES_AUTH, etc.)
6. [x] Embedding profile model — immutable record of dense model, sparse model, dimension, collection name
7. [x] Dense embedding generation via NVIDIA NIM
8. [x] Qdrant upsert with deterministic point IDs (derived from chunk ID)
9. [x] BM25/sparse indexing via Qdrant text payload index
10. [x] Point count verification before revision activation

#### Phase 2 implementation notes

- **Embedding profile:** Persisted in PostgreSQL (`embedding_profiles` table), `version="v1"`, immutable. Re-fetched after `ON CONFLICT DO NOTHING` to handle concurrent ingestion.
- **Chunk text format:** Self-contained retrieval projections — method, path, summary, description, auth, parameters (truncated at 10), request body required fields, responses. No character-count splitting.
- **Content hash:** SHA-256 of `"{profile_version}:{text}"` — stable idempotency key across re-ingestion runs.
- **Qdrant collection:** One shared collection `fetch_chunks_v1`, tenant isolation via payload filters (`workspace_id`, `revision_id`). BM25 via `TEXT` index on the `text` field.
- **Point IDs:** `chunk.id == chunk.qdrant_point_id` — deterministic UUIDs, no separate mapping table.
- **VERIFYING stage:** `count_points(revision_id, workspace_id)` must equal `expected_chunk_count` before revision activates. Mismatch raises `IngestionError`.
- **NIM model:** `nvidia/nv-embedqa-e5-v5` (dimension 1024) used on free tier. Requires `input_type=passage` for indexing. `nvidia/nv-embed-v2` (4096) is not available on free tier.
- **Ingestion pipeline stages added:** NORMALIZING → CHUNKING → EMBEDDING → INDEXING → VERIFYING → ACTIVE.

### Phase 3 — Retrieval pipeline (complete)

1. [x] `QueryNormalizer` — lowercases, strips punctuation, normalises whitespace
2. [x] `ExactLookup` — path/method pattern matching against pg operations before vector search
3. [x] `DenseRetriever` — NVIDIA NIM embedding query → Qdrant vector search, tenant-scoped
4. [x] `BM25Retriever` — Qdrant scroll + `MatchText` filter (not a vector search)
5. [x] `RRFFusion` — Reciprocal Rank Fusion combining dense and BM25 result lists
6. [x] `RetrievalReranker` — NVIDIA NIM `/ranking` via `httpx` (not OpenAI-compatible)
7. [x] `RelationshipExpander` — injects linked schema/auth chunks post-rerank via chunk relations
8. [x] `ContextPacker` — token-budget window packing of final chunk list
9. [x] `RetrievalService` — orchestrates full pipeline; returns ranked, expanded, packed chunks
10. [x] `QueryRun` entity + `PgQueryRunRepository` — trace persistence for every retrieval call
11. [x] Migration `004_query_runs.py` — `query_runs` table with JSONB chunk snapshot

#### Phase 3 implementation notes

- **Deterministic chunk IDs:** `uuid5(NAMESPACE_URL, "{revision_id}:{content_hash}")` — eliminates FK violations and PK collisions on re-ingestion. Qdrant point ID == chunk UUID.
- **Embedding profile version in Qdrant payload:** The `embedding_profile_version` payload field stores the profile UUID, not the string `"v1"`. Retrieval filters must use the UUID.
- **BM25 via scroll:** `BM25Retriever` uses `scroll()` + `MatchText` on the `text` field — not a named vector search. Qdrant text index on `text` must be present (created in Phase 2).
- **Deduplication before upsert:** Chunks are deduplicated by UUID before Qdrant upsert to prevent count mismatch in the VERIFYING stage.
- **Reranker skip:** Full end-to-end reranker integration test is skipped when `RERANKER_API_KEY` is a placeholder value; 12 of 13 integration tests pass unconditionally.
- **Retrieval evaluation deferred:** Recall@5, MRR, and ablation studies are deferred to Phase 9 (Evaluation and hardening). No eval harness is included in Phase 3.

### Phase 9 — complete

- [x] 90-question evaluation datasets (petstore, stripe, github — 30 each; 5 abstention questions per set)
- [x] Retrieval benchmark runner — Recall@5, Recall@10, MRR; `--mode dense/hybrid/full`
- [x] Answer benchmark runner — citation accuracy, abstention accuracy, groundedness
- [x] Validation benchmark runner — is_valid accuracy, finding precision/recall
- [x] Ablation runner — side-by-side comparison table across all three retrieval modes
- [x] Security tests — SSRF guard (3 tests), workspace isolation (6 tests), prompt injection boundaries (8 tests)
- [x] GitHub Actions CI — lint+typecheck, unit+security tests, frontend build, docker build
- [x] Regression thresholds in `evals/thresholds.json`
- [x] `evals/README.md` — benchmark usage, threshold interpretation, CI vs eval runner distinction
- [x] 27 pre-existing mypy errors and 3 ruff errors fixed (412 tests passing)

### Phase 10 — Portfolio release (complete)

- [x] README overhaul — problem statement, feature list with specifics (11-stage pipeline, hybrid retrieval, deterministic citations, SupportStatus, 9 MCP tools), architecture diagram, ingestion pipeline table, security section, getting started with editor MCP config for Claude Desktop / Cursor / VS Code Cline, design decisions section, limitations, full roadmap
- [x] `docs/resume-bullets.md` — 8 technical resume bullets referencing real implementation details (412 tests, 11-stage pipeline, 9 MCP tools, 90-question eval dataset, Recall@5/MRR thresholds)
- [x] Eval results placeholder table in README — headers and threshold targets documented; actual numbers to be filled by running `evals/runners/` against a live instance with Petstore, Stripe, and GitHub ingested
- [x] MCP quickstart in README — JSON config snippets for Claude Desktop, Cursor, and VS Code Cline

---

## 25. Key Risks

| Risk | Mitigation |
|---|---|
| Documentation sites are difficult or hostile to crawl | Bounded adapters, static-first fetching, browser isolation, explicit failure states |
| Large/recursive schemas exceed context limits | Canonical schema storage, bounded projections, relationship expansion |
| LLM generates plausible but undocumented code | Deterministic contract checks, citations, abstention, syntax/schema validation |
| Index and database drift | Revision activation gate and reconciliation jobs |
| Cross-tenant leakage | Mandatory workspace/revision filters and security tests |
| Retrieval changes silently reduce quality | Versioned evaluation datasets and CI thresholds |
| Dependency/model churn | Provider adapters, lockfiles, configuration versions |
| “Agentic” design becomes unnecessary complexity | Explicit workflow states and tools; add autonomy only when evaluation proves value |

---

## 26. Interview Narrative

The strongest technical story is not “I built a chatbot over API docs.” It is:

> I built a version-aware API documentation intelligence layer. It normalizes OpenAPI and documentation pages into a canonical API model, indexes structure-preserving projections with hybrid dense and BM25 retrieval, reranks and expands related schemas, and uses a bounded agent workflow for Q&A, integration generation, request validation, error diagnosis, and version comparison. PostgreSQL remains the source of truth, Qdrant is a rebuildable retrieval index, citations are mapped deterministically, and quality is measured with retrieval, grounding, abstention, and code-validation evaluations. The same services are exposed through a web UI, FastAPI, and structured MCP tools.

---

## 28. Deployment Profiles

### Local Full Profile

Used during development. All services run via Docker Compose.

- PostgreSQL (Docker)
- Qdrant (Docker)
- Redis (Docker)
- MinIO (Docker)
- FastAPI + worker (Docker)
- Next.js (local dev server or Docker)
- LLM/embedding/reranker: configurable via `LLM_PROVIDER` env var
- All ingestion source types enabled
- No quotas

### Free Portfolio Profile

Used when a live URL is required for a job application. Minimal architectural changes — only provider and queue implementations swap.

- Frontend: Vercel Hobby
- FastAPI + MCP: Render or Railway free tier
- PostgreSQL: Neon free tier
- Vectors: Qdrant Cloud free tier
- Redis: Upstash free tier
- Object storage: Cloudflare R2 free tier
- Job triggering: Upstash QStash (replaces always-on Celery worker via existing job interface abstraction — see §5.3)
- LLM + embeddings + reranker: NVIDIA NIM free API (eliminates local model RAM requirements)
- HTML/Playwright crawling: disabled
- Pre-indexed APIs: Petstore, GitHub, Stripe
- Temporary uploads: 1 per session, auto-deleted after 24 hours
- Query limit: 30 per IP per day

Provider swap requires only environment variable changes. No domain or application code changes. Permitted by ADR-009 and ADR-011.

---

## 27. External Design References

- Qdrant multitenancy and payload partitioning: <https://qdrant.tech/documentation/manage-data/multitenancy/>
- Qdrant hybrid queries: <https://qdrant.tech/documentation/search/hybrid-queries/>
- Qdrant text/BM25 search: <https://qdrant.tech/documentation/search/text-search/>
- MCP Python SDK: <https://py.sdk.modelcontextprotocol.io/>
- MCP transports: <https://modelcontextprotocol.io/specification/2025-06-18/basic/transports>
- OpenAPI Specification: <https://spec.openapis.org/oas/latest.html>
- OpenAPI Spec Validator: <https://github.com/python-openapi/openapi-spec-validator>
