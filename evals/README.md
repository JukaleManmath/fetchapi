# Evals

Benchmark runners for retrieval quality, answer quality, and validation accuracy.

## Prerequisites

- A running backend stack (PostgreSQL, Qdrant, and a NIM-compatible endpoint)
- An ingested source. Find active sources by calling:

```bash
curl http://localhost:8000/v1/sources
```

Copy the `id` of the source you want to evaluate — this is your `--source-id`.

---

## Retrieval benchmark

Measures Recall@5, Recall@10, and MRR against a labelled dataset.

```bash
python evals/runners/retrieval_benchmark.py \
  --dataset evals/datasets/petstore.json \
  --source-id <uuid> \
  --mode full \
  --top-k 10
```

**Modes:**

| Mode | Description |
|---|---|
| `dense` | Dense vector search only |
| `hybrid` | Dense + BM25, no reranker |
| `full` | Dense + BM25 + cross-encoder reranker (default) |

Results are written to `evals/results/retrieval_{mode}_{timestamp}.json`.

---

## Answer benchmark

Measures citation accuracy, abstention accuracy, and groundedness. Requires a live LLM endpoint.

```bash
python evals/runners/answer_benchmark.py \
  --dataset evals/datasets/petstore.json \
  --source-id <uuid>
```

Results are written to `evals/results/answer_{timestamp}.json`.

---

## Validation benchmark

Measures is_valid accuracy and finding category precision/recall against the fixture file.

```bash
python evals/runners/validation_benchmark.py \
  --source-id <uuid> \
  --fixtures evals/fixtures/validation/broken_requests.json
```

Results are written to `evals/results/validation_{timestamp}.json`.

---

## Ablation study

Compares dense, hybrid, and hybrid+rerank modes side by side.

```bash
python evals/runners/ablation.py \
  --dataset evals/datasets/petstore.json \
  --source-id <uuid>
```

Prints a comparison table:

```
Mode             Recall@5   Recall@10      MRR
dense              0.XX        0.XX       0.XX
hybrid             0.XX        0.XX       0.XX
hybrid+rerank      0.XX        0.XX       0.XX
```

---

## Thresholds

Minimum acceptable values are defined in `evals/thresholds.json`. Check your results against them manually:

```bash
cat evals/thresholds.json
```

Example: if `retrieval.recall_at_5` threshold is `0.70`, a benchmark result of `0.65` means the pipeline is below threshold and needs investigation.

---

## CI vs. eval runners

| Test type | Runs in CI | Requires live infra |
|---|---|---|
| Unit tests (`tests/unit/`) | Yes | No |
| Security tests (`tests/security/`) | Yes | No |
| Integration tests (`tests/integration/`) | No | Yes (PostgreSQL, Qdrant) |
| Eval runners (`evals/runners/`) | No | Yes (PostgreSQL, Qdrant, NIM API) |

CI runs unit and security tests only. Eval runners and integration tests must be run manually against a live stack.
