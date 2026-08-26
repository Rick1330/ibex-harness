# Memory service (Phase 3 Track B)

Python FastAPI substrate for vector store, composite scoring, embedder client, and
(later) write/read pipelines. **Not** the place for extraction workers (`services/worker/`).

## Status (m3.2.1)

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

## HNSW benches

Live under top-level [`benchmarks/memory/`](../../benchmarks/memory/) (publish-aligned),
not under this service tree. Published JSON:
`web/public/benchmarks/hnsw-benchmark-data.json` (separate from proxy `benchmark-data.json`).

```bash
# compose-test Postgres on :5433, migrated:
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench-smoke   # 10K
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench         # 10K / 100K / 1M
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
