# IBEX Worker service (Phase 3.5 Track A)

Python Celery worker for async extraction, embedding jobs, maintenance sweeps, and MCP
audit tasks. **Skeleton only in m3.5.A.1** — business logic lands in Tracks B–E.

## Redis layout (shared instance)

| Logical role | DB index | Env knob |
| --- | --- | --- |
| Cache (proxy, memory, embedder) | 0 | `REDIS_DB_CACHE` |
| **Celery broker** | 1 | `REDIS_DB_QUEUE` |
| Rate limiting | 2 | `REDIS_DB_RATE_LIMIT` |
| **Celery results** | 3 | `REDIS_DB_RESULTS` |

Override full URLs with `IBEX_WORKER_BROKER_URL` / `IBEX_WORKER_RESULT_BACKEND`, or set
`IBEX_EXTRACTION_REDIS_URL` for a dedicated broker host (falls back to `REDIS_URL`).

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

# Sync deps
cd services/worker && uv sync --extra dev

# Worker (all queues, left-to-right priority)
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
| `IBEX_WORKER_BROKER_URL` | derived | Full Celery broker URL |
| `IBEX_WORKER_RESULT_BACKEND` | derived | Full result backend URL |
| `REDIS_URL` | — | Base URL for derived broker/results |
| `REDIS_DB_QUEUE` | `1` | Broker logical DB |
| `REDIS_DB_RESULTS` | `3` | Result backend logical DB |
| `IBEX_WORKER_MAINTENANCE_BEAT_SECONDS` | `300` | Beat interval for noop sweep |
| `IBEX_WORKER_RESULT_EXPIRES_SECONDS` | `3600` | Result TTL when `ignore_result=False` |

Global default: `task_ignore_result=True` (fire-and-forget). Opt in per task for retry
visibility (m3.5.A.2).

## 3.5.A.2 seam

- `IbexTask` base class holds retry policy; **no** `on_failure` override.
- `app/observability.py` is the attachment point for `@traced_task` and `task_failure`
  signal handlers.

## Tests

```bash
make test-worker
make test-worker-integration   # requires Redis on REDIS_URL
```
