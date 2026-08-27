# Memory service (Phase 3 Tracks B–C)

Python FastAPI substrate for vector store, composite scoring, embedder client, PII
write stage, and (later) full write/read pipelines. **Not** the place for extraction
workers (`services/worker/`).

## Status

### m3.2.1 (Track B)

- Probes: `GET /health`, `GET /ready`, `GET /metrics`
- Composite scoring v2 + category half-life table (`app/scoring/`)
- `VectorStore` ABC + `InMemoryVectorStore` + `PgVectorStore` (`app/vectorstore/`)
  - Per-transaction `SET LOCAL app.current_org_id` + `SET LOCAL hnsw.ef_search`
  - Explicit `org_id` / `agent_id` filters on search; upsert updates embeddings on
    existing memory rows only (row create is Track C)
- Embedder HTTP client (`app/clients/embedding.py`) — `POST /v1/embed`, Bearer token,
  retries 429/502/503 + transport/timeout only; never logs texts/vectors/token
- Config: `IBEX_MEMORY_*`, `IBEX_HNSW_EF_SEARCH`, `IBEX_RANK_WEIGHT_*`, embedder URL/token
- ADR: [ADR-0053](../../web/content/docs/adr/0053-vector-store-abstraction.mdx)
- Image: `ghcr.io/<repo>/memory` via `.github/workflows/docker-publish.yml`

### m3.C.1 (Track C — PII)

- Write-pipeline Stage seam: validate → pii → embed (`app/pipeline/`)
- Presidio two-tier detect/redact + quarantine (`app/pii/`, ADR-0054)
- Defaults: `IBEX_MEMORY_PII_REDACT_MIN_CONFIDENCE=0.70`, `IBEX_MEMORY_PII_SPACY_MODEL=en_core_web_md`
- Typed placeholders (`[EMAIL_ADDRESS]`, …); low-confidence findings → `status=quarantined`
- Benches: [`benchmarks/memory/pii/`](../../benchmarks/memory/pii/)

## HNSW benches

Live under top-level [`benchmarks/memory/`](../../benchmarks/memory/) (publish-aligned),
not under this service tree. Published JSON:
`web/public/benchmarks/hnsw-benchmark-data.json` (separate from proxy `benchmark-data.json`).

```bash
# compose-test Postgres on :5433, migrated:
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench-smoke   # 10K
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench         # 10K / 100K (1M is CI-only — Memory Benchmarks profile full)
```

Site: `/benchmarks/memory`. CI: `.github/workflows/memory-benchmark.yml`.

## Local

From the **repository root**:

```bash
cd services/memory && uv sync --group dev
uv run --directory services/memory uvicorn app.main:app --host 127.0.0.1 --port 8005
make test-memory              # unit (skips integration)
# compose-test Postgres on :5433, migrated:
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make test-memory-integration
```

If you are already inside `services/memory/`, use `make -C ../.. test-memory` (and the
same for `test-memory-integration`).

See [ENVIRONMENT_VARIABLES.md](../../web/engineering/ENVIRONMENT_VARIABLES.md) §11.
