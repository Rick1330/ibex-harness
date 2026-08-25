# Memory service (Phase 3 Track B)

Python FastAPI substrate for vector store, composite scoring, and (later) write/read
pipelines. **Not** the place for extraction workers (`services/worker/`).

## Status (m3.2.1 PR-B)

- Probes: `GET /health`, `GET /ready`, `GET /metrics`
- Composite scoring v2 + category half-life table (`app/scoring/`)
- `VectorStore` ABC + `InMemoryVectorStore` + `PgVectorStore` (`app/vectorstore/`)
  - Per-transaction `SET LOCAL app.current_org_id` + `SET LOCAL hnsw.ef_search`
  - Explicit `org_id` / `agent_id` filters on search; upsert updates embeddings on
    existing memory rows only (row create is Track C)
- Config: `IBEX_MEMORY_*`, `IBEX_HNSW_EF_SEARCH`, `IBEX_RANK_WEIGHT_*`
- Follow-up: embedder HTTP client + HNSW benches + ADR-0053 (PR-C)

## Local

```bash
cd services/memory
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8005
make test-memory              # unit (skips integration)
# compose-test Postgres on :5433, migrated:
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make test-memory-integration
```

See [ENVIRONMENT_VARIABLES.md](../../web/engineering/ENVIRONMENT_VARIABLES.md) §11.
