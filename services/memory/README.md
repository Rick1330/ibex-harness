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

### m3.C.2 (Track C — Dedup)

- Stages: exact_dedup → embed → near_dedup (`app/dedup/`, ADR-0055)
- Exact: SHA-256 of normalized post-PII content; bump `retrieval_count` on hit; skip embed
- Near: `VectorStore.search` with `IBEX_MEMORY_NEAR_DUPLICATE_SIM_THRESHOLD` (default 0.92, strict `>`)
- Partial unique index: `000018_memories_content_hash_unique_active`
- Metric: `ibex_memory_dedup_total{result=exact_duplicate|near_duplicate|novel}`

### m3.C.3 (Track C — Temporal conflict)

- Stage: `conflict` after near_dedup (`app/conflict/`, ADR-0056)
- Interval-overlap-first: same subject + newer `valid_from` + non-overlapping →
  `supersedes` (zero LLM); overlap / missing `valid_from` → pluggable classifier
- Persist helpers: `apply_supersession`, `insert_relationship` (org-scoped)
- Metrics: `ibex_memory_conflicts_total{outcome}`, `ibex_memory_conflict_llm_calls_total`
- Toggle: `IBEX_MEMORY_CONFLICT_DETECTION_ENABLED` (default true)

### m3.C.4 (Track C — Multi-label classification)

- Optional `labels[]` on `POST /v1/memories` (1–5 labels, per-label confidence; ADR-0048)
- `app/write/labels.py` — `resolve_write_labels`, validation, backward-compat synthesis from scalar `category` + `confidence` when `labels` omitted
- Transactional `insert_labels_session` + `reload_memory_session` in orchestrator (same txn as memory insert); app never `UPDATE memories.category` — trigger `sync_memory_primary_category` only
- Empty explicit `labels: []` → `ValidationError`; duplicate label → `409`-class validation error
- Milestone: [3.C.4](../../web/content/roadmap/phase-3-memory-engine/milestones/3.c.4-multi-label-classification.mdx); tracking [#630](https://github.com/Rick1330/ibex-harness/issues/630)

### m3.C.5 (Track C — Write orchestration)

- `POST /v1/memories` — documented contract ([API_DOCUMENTATION.md](../../web/engineering/API_DOCUMENTATION.md))
- Pipeline steps 7–9: transactional insert + supersession + escalations (`app/write/`, ADR-0057)
- Unique-violation on active content hash → bump + `409 DUPLICATE_CONTENT`
- After-commit Redis cache (`{org_id}:memory:{memory_id}`, `{org_id}:hot_memories:{agent_id}`) + vector upsert
- `memory_conflict_escalations` table (migration `000019`)
- Auth: gRPC `ValidateToken` (`IBEX_AUTH_GRPC_ADDR`); permission `memory:write`
- Idempotency: `X-Idempotency-Key` via Redis (`idempotency:{org_id}:{key}`)
- Observability: Prometheus job `memory` (:8005), Grafana dashboard `memory.json`

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
