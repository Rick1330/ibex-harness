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
dedicated test database (or `IBEX_WORKER_DESTRUCTIVE_INTEGRATION_TESTS=1` to opt in). CI sets
`POSTGRES_TEST_DSN` via `infra/scripts/worker-integration-test-ci.sh`.
