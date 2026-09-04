# IBEX Worker service (Phase 3.5 Track A)

Python Celery worker for async extraction, embedding jobs, maintenance sweeps, and MCP
audit tasks. **Skeleton in m3.5.A.1**; **observability + dead-letter in m3.5.A.2** —
business logic lands in Tracks B–E.

## Redis layout (shared instance)

| Logical role | DB index | Env knob |
| --- | --- | --- |
| Cache (proxy, memory, embedder) | 0 | `REDIS_DB_CACHE` |
| **Celery broker** | 1 | `REDIS_DB_QUEUE` |
| Rate limiting | 2 | `REDIS_DB_RATE_LIMIT` |
| **Celery results** | 3 | `REDIS_DB_RESULTS` |

Override broker-only with `IBEX_WORKER_BROKER_URL` or result-only with
`IBEX_WORKER_RESULT_BACKEND`. Set `IBEX_EXTRACTION_REDIS_URL` (or `REDIS_URL`) to change
the **shared base host** used to derive **both** broker and result-backend URLs
(unless overridden individually).

> **Note:** `TECH_STACK.md` shows broker `/0` and result `/1` — worker uses the
> `ENVIRONMENT_VARIABLES.md` DB allocation above to avoid cache key collisions.

## Queue topology

| Queue | Purpose | Priority |
| --- | --- | --- |
| `extraction` | Session → memory extraction | Cross-queue first; intra-queue Redis priority 0–9 |
| `embedding` | Async embedding jobs | After extraction |
| `maintenance` | Beat sweeps / housekeeping | After embedding |
| `mcp_audit` | MCP tool audit fan-out | Lowest |

**Priority mechanism:** `x-max-priority` is RabbitMQ-only and **not** used. Cross-queue
order is worker `-Q extraction,embedding,maintenance,mcp_audit`. Intra-extraction priority
uses Celery Redis `broker_transport_options.priority_steps` (0–9).

## Run locally

```bash
# Infra
make compose-dev-up
make db-migrate

# Sync deps
cd services/worker && uv sync --extra dev

# Worker (all queues, left-to-right priority)
export POSTGRES_DSN='postgres://ibex:ibex@127.0.0.1:5432/ibex?sslmode=disable'
OTEL_EXPORTER_OTLP_ENDPOINT='http://127.0.0.1:4317' \
celery -A app.celery_app:celery_app worker \
  -Q extraction,embedding,maintenance,mcp_audit \
  --loglevel=info

# Beat (maintenance noop sweep)
celery -A app.celery_app:celery_app beat --loglevel=info

# Health ping
make worker-ping
```

Or use Makefile targets: `make worker-dev`, `make worker-beat-dev`, `make test-worker`.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `IBEX_WORKER_BROKER_URL` | derived | Full Celery broker URL (broker-only override) |
| `IBEX_WORKER_RESULT_BACKEND` | derived | Full result backend URL (result-only override) |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` | Shared base URL for derived broker/results |
| `REDIS_DB_QUEUE` | `1` | Broker logical DB |
| `REDIS_DB_RESULTS` | `3` | Result backend logical DB |
| `IBEX_WORKER_DATABASE_URL` / `POSTGRES_DSN` | (none) | Postgres DSN for dead-letter persistence |
| `IBEX_WORKER_METRICS_PORT` | `8006` | Prometheus `/metrics` HTTP port |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | (none) | OTLP gRPC collector (optional) |
| `OTEL_SAMPLE_RATIO` | `0.01` | Trace sampling ratio |
| `IBEX_WORKER_MAINTENANCE_BEAT_SECONDS` | `300` | Beat interval for noop sweep |
| `IBEX_WORKER_RESULT_EXPIRES_SECONDS` | `3600` | Result TTL when `ignore_result=False` |
| `IBEX_WORKER_EXTRACTION_PROVIDER` | `openai` | `openai` or `vllm` |
| `OPENAI_API_KEY` | (none) | Required for `openai` |
| `IBEX_WORKER_EXTRACTION_BASE_URL` | (none) | Required for `vllm` |
| `IBEX_WORKER_MEMORY_BASE_URL` | (none) | Memory service origin |
| `IBEX_WORKER_MEMORY_API_TOKEN` | (none) | Bearer with `memory:write` |
| `CLICKHOUSE_DSN` | (none) | Empty skips `llm_traces` insert |

Global default: `task_ignore_result=True` (fire-and-forget). Opt in per task for retry
visibility.

## Observability (m3.5.A.2)

- **OTel:** `IbexTask.__call__` wraps every task in a span (`ibex-worker` tracer). See [ADR-0062](/docs/adr/0062-worker-task-observability-dead-letter).
- **Dead-letter:** `task_failure` signal persists exhausted-retry failures to `ibex_core.failed_tasks` and increments `ibex_worker_task_dead_letter_total{task_name}`.
- **Metrics:** `GET :8006/metrics` when worker process is running (`ibex_process_up`, dead-letter counter).
- **Alert:** `IBEXWorkerTaskDeadLettered` in `infra/monitoring/prometheus/rules/ibex-worker.yml`.

### Local verification

```bash
make observability-up          # Prometheus/Grafana/Tempo
make compose-dev-up
make db-migrate

# Trigger test failure (maintenance queue)
cd services/worker
uv run celery -A app.celery_app:celery_app call ibex.worker.maintenance.always_fail

# Postgres dead-letter row
psql "$POSTGRES_DSN" -c \
  "SELECT task_name, retry_count, left(traceback,80) FROM ibex_core.failed_tasks ORDER BY failed_at DESC LIMIT 1;"

# Prometheus counter (after worker running with metrics port exposed)
curl -s localhost:8006/metrics | grep ibex_worker_task_dead_letter_total
```

Integration test task `ibex.worker.maintenance.always_fail` exercises the full retry → dead-letter path.

## Architecture seams

- `IbexTask` base class holds retry policy; **no** `on_failure` override (signals in `app/observability.py`).
- `app/task_lifecycle.py` — structured start/complete logging via `task_prerun` / `task_postrun`.
- `app/observability.py` — OTel spans, Prometheus metrics, dead-letter handler.

## Tests

```bash
make test-worker
make test-worker-integration   # requires Redis + POSTGRES_TEST_DSN (or POSTGRES_DSN) + migrated DB
```

Integration tests that `TRUNCATE ibex_core.failed_tasks` require `POSTGRES_TEST_DSN` pointing at a
dedicated test database. CI sets `POSTGRES_TEST_DSN` via `infra/scripts/worker-integration-test-ci.sh`.

## Manual vLLM verification (not CI)

CI has **no GPU runner**. The self-hosted path (`IBEX_WORKER_EXTRACTION_PROVIDER=vllm`) is
covered in unit tests with `httpx.MockTransport` only. Live verification against a real
vLLM process is **manual** — do not treat the mocked unit tests as satisfying a live
integration signal.

### Stand up Qwen2.5-14B-Instruct

```bash
# Example: OpenAI-compatible vLLM server (adjust GPU flags / model to your hardware)
docker run --gpus all -p 8000:8000 vllm/vllm-openai:latest \
  --model Qwen/Qwen2.5-14B-Instruct \
  --served-model-name Qwen2.5-14B-Instruct

# If 14B VRAM does not fit, substitute Qwen2.5-7B-Instruct and set:
# IBEX_WORKER_EXTRACTION_VLLM_MODEL=Qwen2.5-7B-Instruct
# with --served-model-name Qwen2.5-7B-Instruct (must match the env value)
```

### Point the worker at vLLM

```bash
export IBEX_WORKER_EXTRACTION_PROVIDER=vllm
export IBEX_WORKER_EXTRACTION_BASE_URL=http://127.0.0.1:8000/v1
export IBEX_WORKER_MEMORY_BASE_URL=http://127.0.0.1:8005
export IBEX_WORKER_MEMORY_API_TOKEN='…'  # memory:write PAT; never commit
# Optional: CLICKHOUSE_DSN for llm_traces; empty skips insert fail-open
```

Enqueue `ibex.worker.extraction.extract_session_memories` with a completed-session payload
(`org_id`, `agent_id`, `session_id`, `turns` list).

### What confirms correctness

1. Worker task returns `status=ok` (or `skipped` only for intentional session gates).
2. Model content is JSON matching `BatchExtractionResult`:
   `{"turns":[{"turn_index":0,"memories":[…]}]}` with **no** markdown fences.
3. Memory service receives one POST per extracted memory with matching `session_id` /
   labels / optional temporal fields.
4. If `CLICKHOUSE_DSN` is set, `ibex.llm_traces` gains a row with `provider=vllm`,
   token counts, and **no** prompt/completion text.

This path is **not run in CI**. A GPU-backed integration job remains an explicit follow-up
when a GPU runner exists — do not silently check that box.

## Extraction quality eval (m3.5.B.4 / ADR-0066)

Gold-set harness under `eval/` (cassette CI for OpenAI; vLLM manual side-by-side).

```bash
cd services/worker
.venv/bin/pytest -q eval/
.venv/bin/python eval/run_eval.py --mode cassette
.venv/bin/python eval/regression_gate.py   # exit 1 on >3pp CI regression
```

- Gold set docs: [`eval/gold_set/v1/README.md`](eval/gold_set/v1/README.md)
- Workflow: `.github/workflows/extraction-eval.yml` (smoke/fast/full)
- Site: `/benchmarks/extraction-quality`
- Manual vLLM metrics: run `--mode vllm` after the section above, then update
  `baseline_results.json` `providers.vllm` (`enforcement` stays `manual`)
