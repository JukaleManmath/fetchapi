# Phase 9 — Evaluation and Hardening

## Rules (non-negotiable)
- Do NOT use cmux. Do NOT spawn new panes. Do NOT create sub-agents.
- Implement directly in this session.
- No fabricated metrics. No hardcoded results.
- All datetimes: `datetime.now(UTC)`. All enums: `StrEnum`. `AsyncIterator` from `collections.abc`.
- Use venv at `/Users/manmathjukale/Desktop/AI Projects/fetchAPI/backend/.venv/bin/python`.
- Work in `/Users/manmathjukale/Desktop/AI Projects/fetchAPI-phase9/`.

## Context

Existing structure:
- `evals/datasets/` — empty, needs dataset JSON files
- `evals/fixtures/validation/broken_requests.json` — 15 validation fixtures already exist
- `evals/runners/` — empty, needs benchmark runners
- `evals/results/` — empty, benchmark output goes here
- `backend/tests/integration/test_retrieval.py` — existing integration tests
- `backend/tests/fixtures/openapi/` — edge case specs including prompt injection fixtures
- `examples/petstore/openapi.json` — 19 operations, schemas: Order/Category/User/Tag/Pet/ApiResponse
- `examples/stripe/openapi.json` — 587 operations
- `examples/github/openapi.json` — 962 operations

Read the following before writing code:
- `backend/src/fetch/application/retrieval/service.py` — RetrievalService.retrieve() signature and RetrievalConfig
- `backend/src/fetch/application/retrieval/dense_retriever.py` — DenseRetrievalConfig
- `backend/src/fetch/application/retrieval/bm25_retriever.py` — BM25RetrievalConfig
- `backend/src/fetch/application/retrieval/fusion.py` — FusionConfig
- `backend/src/fetch/application/retrieval/reranker.py` — RerankConfig
- `backend/src/fetch/application/retrieval/expander.py` — ExpansionConfig
- `backend/src/fetch/application/retrieval/packer.py` — ContextPacker, PackedContext
- `backend/src/fetch/application/queries/service.py` — QueryService.stream()
- `backend/src/fetch/application/validation/service.py` — ValidationService.validate_curl()
- `backend/src/fetch/config.py` — get_settings()
- `backend/src/fetch/infrastructure/db/repositories.py` — repository constructors
- `backend/src/fetch/infrastructure/db/session.py` — get_session()
- `backend/src/fetch/api/v1/dependencies.py` — how services are constructed (mirror this)
- `backend/src/fetch/domain/entities.py` — Citation, QueryRun entities

---

## Step 1 — Evaluation datasets

### `evals/datasets/petstore.json`

Write 30 questions grounded in the Petstore spec (paths: /pet, /pet/findByStatus, /pet/findByTags, /pet/{petId}, /pet/{petId}/uploadImage, /store/inventory, /store/order, /store/order/{orderId}, /user, /user/createWithList, /user/login, /user/logout, /user/{username}; schemas: Order, Category, User, Tag, Pet, ApiResponse; security: petstore_auth (OAuth2), api_key).

Format:
```json
[
  {
    "id": "p001",
    "question": "How do I add a new pet to the store?",
    "expected_operation": "POST /pet",
    "expected_entity_type": "operation",
    "expected_citation_contains": ["POST", "/pet"],
    "should_abstain": false
  }
]
```

Include:
- 10 operation lookup questions (e.g. "how do I find pets by status?", "how do I delete a pet?", "how do I upload a pet image?", "how do I place an order?", "how do I get store inventory?", "how do I create a user?", "how do I log in?")
- 5 parameter questions (e.g. "what parameters does GET /pet/findByStatus take?", "what is the petId parameter type?")
- 5 auth questions (e.g. "what auth does POST /pet require?", "what scopes does petstore_auth have?")
- 5 schema questions (e.g. "what fields does the Pet schema have?", "what is the Order schema?")
- 5 abstention questions — things NOT in the spec (e.g. "how do I pay for a pet?", "how do I cancel a subscription?", "what is the rate limit?", "how do I get a refund?", "what are the webhook events?"). Set `should_abstain: true` and `expected_operation: null`.

### `evals/datasets/stripe.json`

Write 30 questions grounded in the Stripe spec. Use paths like /v1/charges, /v1/customers, /v1/payment_intents, /v1/subscriptions, /v1/invoices, /v1/refunds, /v1/products, /v1/prices, /v1/account, /v1/webhooks.

Same format. Include 5 abstention questions about things clearly not in a payments API.

### `evals/datasets/github.json`

Write 30 questions grounded in the GitHub GHES API. Use paths like /repos/{owner}/{repo}, /repos/{owner}/{repo}/issues, /repos/{owner}/{repo}/pulls, /users/{username}, /orgs/{org}, /search/repositories, /gists, /admin/hooks.

Same format. Include 5 abstention questions.

---

## Step 2 — Retrieval benchmark runner

### `evals/runners/retrieval_benchmark.py`

A standalone async script. Run with:
```bash
python evals/runners/retrieval_benchmark.py --dataset evals/datasets/petstore.json --source-id <uuid>
```

Arguments:
- `--dataset` — path to dataset JSON
- `--source-id` — UUID of the ingested source to evaluate against
- `--top-k` — int, default 10
- `--mode` — "full" (dense+bm25+rerank), "hybrid" (dense+bm25, no rerank), "dense" (dense only). Default "full".
- `--output` — optional path to write JSON results. Default: `evals/results/retrieval_{mode}_{timestamp}.json`

Logic:
1. Load dataset JSON
2. Build database session and construct RetrievalService (mirror how api/v1/dependencies.py does it — read that file first)
3. Resolve the active revision_id for the given source_id from PostgreSQL
4. For each question with `should_abstain: false`:
   a. Call `RetrievalService.retrieve(question, source_id, revision_id, workspace_id, ...)`
   b. Look through `packed.citations` for one where `f"{citation.method} {citation.path}"` matches `expected_operation` (case-insensitive) OR `citation.entity_type` matches `expected_entity_type`
   c. Record rank position (1-based index in citations list), or None if not found
   d. Compute reciprocal rank = 1/rank if rank <= top_k else 0
5. Compute:
   - Recall@5: fraction of questions where rank <= 5
   - Recall@10: fraction of questions where rank <= 10
   - MRR: mean reciprocal rank across all non-abstention questions
6. Print summary table to stdout
7. Write full results to output JSON

For `--mode hybrid`: set `RerankConfig.top_n = 0` or skip the reranker by passing a dummy config that disables it. Read the RerankConfig fields first to find the right way.

For `--mode dense`: additionally pass an empty/no-op BM25 config so only dense results are used.

Use `asyncio.run(main())` at the bottom.

Import from `backend/src/fetch/` using `sys.path.insert(0, "backend/src")`.

---

## Step 3 — Answer benchmark runner

### `evals/runners/answer_benchmark.py`

Arguments: `--dataset`, `--source-id`, `--output`

Logic:
1. For each question:
   a. Call `QueryService.stream()` — collect all events
   b. Capture: full answer text, final citations, support_status
   c. **Citation accuracy** (non-abstention questions): did any citation's method+path match `expected_operation`? Binary hit/miss.
   d. **Abstention accuracy**: if `should_abstain: true`, did `support_status` equal `INSUFFICIENT_EVIDENCE`? If `should_abstain: false`, did it NOT abstain?
   e. **Groundedness**: do any terms from `expected_citation_contains` appear in the answer text? (case-insensitive)

2. Compute:
   - Citation accuracy: correct hits / non-abstention questions
   - Abstention accuracy: correct abstentions / all questions
   - Groundedness: grounded answers / non-abstention questions

3. Print + write results JSON.

Build QueryService the same way the API route does — read `backend/src/fetch/api/v1/queries.py` for the dependency pattern.

---

## Step 4 — Validation benchmark runner

### `evals/runners/validation_benchmark.py`

Arguments: `--fixtures` (default `evals/fixtures/validation/broken_requests.json`), `--source-id`, `--output`

Logic:
1. Load fixtures
2. For each fixture, call `ValidationService.validate_curl(source_id, curl_command)`
3. Check that `result.is_valid == expected_is_valid`
4. Check that each `expected_findings[].category` appears in the actual findings
5. Compute precision/recall on finding categories

Print + write results JSON.

---

## Step 5 — Ablation runner

### `evals/runners/ablation.py`

Arguments: `--dataset`, `--source-id`, `--output`

Runs the retrieval benchmark three times with different modes (dense, hybrid, full) and prints a comparison table:

```
Mode          Recall@5    Recall@10   MRR
dense         0.XX        0.XX        0.XX
hybrid        0.XX        0.XX        0.XX
hybrid+rerank 0.XX        0.XX        0.XX
```

Reuse the retrieval logic from `retrieval_benchmark.py` — extract the core eval function so it can be called with different configs.

---

## Step 6 — Security tests

### `backend/tests/security/__init__.py` — empty

### `backend/tests/security/test_ssrf.py`

Test that ingest rejects SSRF targets. Read how `$ref` resolution works in `backend/src/fetch/infrastructure/openapi/` to understand what error to expect.

```python
import pytest
from fetch.infrastructure.openapi.ref_resolver import resolve_refs  # or whatever the actual module is
# Read the actual resolver module path first

@pytest.mark.asyncio
async def test_ssrf_loopback_blocked():
    """$ref to 127.0.0.1 must be rejected."""
    ...

@pytest.mark.asyncio
async def test_ssrf_private_network_blocked():
    """$ref to 10.0.0.1 must be rejected."""
    ...

@pytest.mark.asyncio
async def test_ssrf_metadata_endpoint_blocked():
    """$ref to 169.254.169.254 must be rejected."""
    ...
```

Read the actual SSRF guard implementation before writing these tests — find the right module and exception class.

### `backend/tests/security/test_workspace_isolation.py`

Test that retrieval is workspace-scoped. This is a unit test using mocked repositories — no real infra needed.

```python
def test_qdrant_filter_always_includes_workspace_id():
    """Verify the Qdrant filter builder always includes workspace_id."""
    # Read QdrantRepository._build_filter or equivalent
    # Assert workspace_id is always in the filter conditions
```

Read `backend/src/fetch/infrastructure/qdrant/repository.py` to find the filter building logic.

### `backend/tests/security/test_prompt_injection.py`

Unit test — no LLM call needed.

```python
def test_prompt_contains_injection_boundary():
    """System prompt must include instruction not to follow document instructions."""
    from fetch.application.queries.prompt import build_system_prompt
    prompt = build_system_prompt()
    # Check that the prompt contains guardrail language
    assert any(phrase in prompt.lower() for phrase in [
        "do not follow", "untrusted", "ignore instructions", "document"
    ])

def test_evidence_block_is_bounded():
    """Evidence is injected inside a delimited block, not inline."""
    from fetch.application.queries.prompt import build_user_message
    # Build a message with mock citations and verify the evidence block
    # has clear start/end delimiters separating it from the question
```

Read `backend/src/fetch/application/queries/prompt.py` to find the actual prompt structure before writing assertions.

---

## Step 7 — GitHub Actions CI

### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  backend-lint-typecheck:
    name: Backend — lint and typecheck
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        working-directory: backend
        run: |
          python -m venv .venv
          .venv/bin/pip install -e ".[dev]"
      - name: Lint
        working-directory: backend
        run: .venv/bin/python -m ruff check src/
      - name: Format check
        working-directory: backend
        run: .venv/bin/python -m ruff format --check src/
      - name: Typecheck
        working-directory: backend
        run: .venv/bin/python -m mypy src/fetch/

  backend-unit-tests:
    name: Backend — unit tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        working-directory: backend
        run: |
          python -m venv .venv
          .venv/bin/pip install -e ".[dev]"
      - name: Unit tests
        working-directory: backend
        env:
          APP_SECRET_KEY: test-secret-key
          LLM_API_KEY: test
          EMBEDDINGS_API_KEY: test
          RERANKER_API_KEY: test
        run: |
          PYTHONPATH=src .venv/bin/python -m pytest tests/unit/ tests/security/ -x -q

  frontend-build:
    name: Frontend — type check and build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: frontend/package-lock.json
      - name: Install dependencies
        working-directory: frontend
        run: npm ci
      - name: Build
        working-directory: frontend
        run: npm run build

  docker-build:
    name: Docker — build image
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build API image
        run: docker compose -f infra/compose.yaml build api
```

Note: integration tests and eval runners are NOT in CI — they require live infra and NIM API keys.

---

## Step 8 — Regression thresholds

### `evals/thresholds.json`

```json
{
  "retrieval": {
    "recall_at_5": 0.70,
    "recall_at_10": 0.80,
    "mrr": 0.60
  },
  "answer": {
    "citation_accuracy": 0.70,
    "abstention_accuracy": 0.85,
    "groundedness": 0.70
  },
  "validation": {
    "finding_precision": 0.75,
    "finding_recall": 0.70,
    "is_valid_accuracy": 0.90
  }
}
```

---

## Step 9 — `evals/README.md`

Write a short README explaining:
- How to run each benchmark (with example commands)
- What `--source-id` to use (run `GET /v1/sources` to find active sources)
- What thresholds mean and how to check against them
- That CI runs unit + security tests only; eval runners require live infra

---

## Step 10 — Verify

```bash
cd /Users/manmathjukale/Desktop/AI Projects/fetchAPI-phase9/backend

# Lint
/Users/manmathjukale/Desktop/AI Projects/fetchAPI/backend/.venv/bin/python -m ruff check src/ tests/
/Users/manmathjukale/Desktop/AI Projects/fetchAPI/backend/.venv/bin/python -m ruff format --check src/ tests/

# Typecheck
/Users/manmathjukale/Desktop/AI Projects/fetchAPI/backend/.venv/bin/python -m mypy src/fetch/

# Unit + security tests
PYTHONPATH=src APP_SECRET_KEY=test LLM_API_KEY=test EMBEDDINGS_API_KEY=test RERANKER_API_KEY=test \
  /Users/manmathjukale/Desktop/AI Projects/fetchAPI/backend/.venv/bin/python -m pytest tests/unit/ tests/security/ -x -q
```

Fix all failures. Do not skip or suppress.

---

## Done signal

When all steps complete, lint is clean, mypy passes, and unit+security tests pass output exactly:

RESULT: Phase 9 implementation complete
