# Local development — Docker Compose

Pinned dependency stack for IBEX Harness local development. **No application services** are defined here — only data stores. Application processes (`proxy`, `auth`, later `embedder` / `memory` / …) run on the host via Make targets.

Roadmap timing for app services: [`services/README.md`](../../../services/README.md). Env registry: [ENVIRONMENT_VARIABLES.md](../../../web/engineering/ENVIRONMENT_VARIABLES.md).

## Prerequisites

- Docker Engine + Docker Compose v2

## Start

From this directory:

```bash
docker compose --env-file .env.example up -d
```

Optional: copy `.env.example` to `.env` and customize ports or credentials.

## Stop

```bash
docker compose down
```

Remove volumes (destructive):

```bash
docker compose down -v
```

## Services and ports

| Service | Image | Host ports | Purpose |
|---------|-------|------------|---------|
| Postgres + pgvector | `pgvector/pgvector:pg16` | 5432 | Primary OLTP (+ vector; HNSW-capable for Phase 3+) |
| Redis Stack | `redis/redis-stack:7.4.0-v1` | 6379 | Cache, Bloom/Cuckoo filters, Celery broker later |
| ClickHouse | `clickhouse/clickhouse-server:24.8.14.39` | 8123 (HTTP), **9002** (native) | Analytics / `llm_traces` |
| MinIO | `minio/minio:RELEASE.2024-12-18T13-15-44Z` | 9000 (API), 9001 (console) | Object storage |

ClickHouse **native** is mapped to host port **9002** so it does not conflict with MinIO on **9000**. Use HTTP (`8123`) for typical local DSNs — see [ENVIRONMENT_VARIABLES.md](../../../web/engineering/ENVIRONMENT_VARIABLES.md).

## Planned compose profiles (not required yet)

When Phase **2.5+** needs local GPU/embedding or self-hosted LLM reference stacks, prefer optional Compose **profiles** (e.g. TEI sidecar, vLLM) rather than bloating the default `up`. Those profiles should be documented here when added, with evidence they are useful for day-to-day dev — not speculative scaffolding.

## Apply database migrations

From the repository root (with containers healthy):

```bash
make db-migrate
make clickhouse-migrate
```

See [ADR-0005](../../../web/content/docs/adr/0005-postgres-migration-strategy.mdx) and `make db-version` / `make db-migrate-down` (dev rollback, one step).

## Verify health

Wait until all containers are healthy (`docker compose ps`), then:

```bash
# Postgres
docker compose exec postgres pg_isready -U ibex -d ibex

# Redis
docker compose exec redis redis-cli ping

# ClickHouse HTTP
curl -s http://localhost:8123/ping

# MinIO (console: http://localhost:9001 — minioadmin / minioadmin from .env.example)
curl -s -o /dev/null -w "%{http_code}" http://localhost:9000/minio/health/live
```

Expected: `pg_isready` accepting connections, Redis `PONG`, ClickHouse body `Ok`, MinIO HTTP `200`.

## Validate compose file only

```bash
docker compose --env-file .env.example config
```
