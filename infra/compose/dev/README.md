# Local development — Docker Compose

Pinned local stack for IBEX Harness. The default file includes data stores **and** two worker application services; proxy, AuthService, API, memory, context, embedder, and MCP processes normally run on the host through their service commands.

## Prerequisites and start

- Docker Engine with Compose v2
- GNU Make, Go, Python/uv, Node/pnpm for host processes

```bash
cp .env.example .env # local credentials only; never commit
cd infra/compose/dev
docker compose --env-file .env up -d
```

## Services and ports

| Service | Host ports | Purpose | Health semantics |
| --- | --- | --- | --- |
| Postgres + pgvector | 5432 | OLTP and vectors | Compose healthcheck |
| Redis Stack | 6379 | Cache, rate limits, Celery broker/results | Compose healthcheck |
| ClickHouse | 8123 HTTP, 9002 native | Analytics and audit/traces | Compose healthcheck |
| MinIO | 9000 API, 9001 console | Object storage | Init + liveness checks |
| `worker` | 8006 metrics, 8007 enqueue/health | Celery extraction, billing, deletion, dead-letter tasks | No Compose healthcheck; verify process, `/health`, and metrics |
| `worker-beat` | none | Scheduled task dispatch | Verify process/logs; no HTTP healthcheck |

The worker services build from `services/worker/Dockerfile`, use the shared Redis/Postgres settings, and require a non-empty `IBEX_WORKER_ENQUEUE_API_TOKEN` to start the enqueue HTTP surface. Never use `.env.example` credentials outside local development.

## Stop and destructive cleanup

```bash
docker compose down
# destructive: removes local volumes
docker compose down -v
```

## Migrations and probes

From the repository root after stores are healthy:

```bash
make db-migrate
make clickhouse-migrate
make worker-ping
make compose-dev-config
```

```bash
docker compose exec postgres pg_isready -U ibex -d ibex
docker compose exec redis redis-cli ping
curl -s http://localhost:8123/ping
curl -s http://localhost:8006/metrics
curl -s http://localhost:8007/health
```

TEI/vLLM GPU profiles are optional and are not part of the default `up`; document any added profile with a tested source/image and security boundary.
