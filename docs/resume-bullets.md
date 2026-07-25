# FetchAPI — Resume Bullets

- **FetchAPI** — designed and built a self-hosted MCP server and API documentation intelligence layer in Python/FastAPI, exposing 9 structured tools to AI coding assistants (Claude Desktop, Cursor, VS Code Cline) through a Streamable HTTP MCP endpoint backed by a clean four-layer architecture (domain → application → infrastructure → entrypoints)

- **FetchAPI** — implemented an 11-stage idempotent ingestion pipeline (QUEUED → FETCHING → SNAPSHOTTING → PARSING → VALIDATING → NORMALIZING → CHUNKING → EMBEDDING → INDEXING → VERIFYING → ACTIVE) with SHA-256 content-addressed MinIO snapshots, SSRF-guarded `$ref` resolution, and atomic revision activation that prevents partial indexes from ever becoming active

- **FetchAPI** — built a hybrid retrieval pipeline combining NVIDIA NIM dense embeddings (1024-dim, Qdrant ANN), BM25 sparse search (Qdrant text index), Reciprocal Rank Fusion, cross-encoder reranking (NIM `/ranking`), and relationship expansion to inject linked schema and auth chunks post-rerank; evaluated against a 90-question dataset targeting Recall@5 ≥ 0.70 and MRR ≥ 0.60 across three retrieval modes (dense, BM25, hybrid+rerank)

- **FetchAPI** — implemented deterministic citation extraction for grounded Q&A: the model emits allowed source IDs from retrieved context; the server owns citation metadata and verifies every ID against the active revision, making hallucinated citations structurally impossible; answers carry a `SupportStatus` enum (SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED) instead of uncalibrated confidence percentages

- **FetchAPI** — built request validation from curl commands using `jsonschema` validation against the canonical spec model (not LLM inference): curl parsing → operation matching → parameter and request body schema validation → corrected example generation; evaluated against 15 broken curl fixtures targeting `is_valid` accuracy ≥ 0.90

- **FetchAPI** — wrote 412 tests across unit, integration, and security suites: 3 SSRF guard tests, 6 workspace isolation tests, 8 prompt injection boundary tests, and regression thresholds in `evals/thresholds.json` enforced by GitHub Actions CI (lint + typecheck + unit + security tests + frontend build + Docker build)

- **FetchAPI** — implemented SSRF protection using `socket.getaddrinfo()` to resolve hostnames to IP addresses before any network fetch, blocking loopback, private RFC-1918, link-local, metadata service, and multicast ranges; enforced YAML alias-expansion DoS cap (100 expansions, configurable) on the raw node tree before `yaml.safe_load()` constructs Python objects

- **FetchAPI** — built a Next.js 15 web UI covering the full workflow — source ingestion, grounded chat with SSE streaming and inline citations, operation and schema explorer, integration code generation panel, curl validation panel, and retrieval inspector showing ranked chunks with scores and citation matches for every query
