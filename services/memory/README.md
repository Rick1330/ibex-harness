# Memory service (Phase 3 Track B)

Python FastAPI substrate for vector store, composite scoring, and (later) write/read
pipelines. **Not** the place for extraction workers (`services/worker/`).

## Status (m3.2.1 PR-A)

- Probes: `GET /health`, `GET /ready`, `GET /metrics`
- Composite scoring v2 + category half-life table (`app/scoring/`)
- Config: `IBEX_MEMORY_*`, `IBEX_HNSW_EF_SEARCH`, `IBEX_RANK_WEIGHT_*`
- Follow-ups: PgVectorStore (PR-B), embedder HTTP client + benches + ADR-0053 (PR-C)

## Local

```bash
cd services/memory
uv sync --group dev
uv run uvicorn app.main:app --host 127.0.0.1 --port 8005
make test-memory   # from repo root
```

See [ENVIRONMENT_VARIABLES.md](../../web/engineering/ENVIRONMENT_VARIABLES.md) §11.
