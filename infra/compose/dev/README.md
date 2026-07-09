# Local development — Docker Compose

Pinned dependency stack for IBEX Harness local development. **No application services** are defined here—only data stores.

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
| Postgres + pgvector | `pgvector/pgvector:pg16` | 5432 | Primary OLTP |
| Redis Stack | `redis/redis-stack:7.4.0-v1` | 6379 | Cache, Bloom/Cuckoo filters |
| ClickHouse | `clickhouse/clickhouse-server:24.8.14.39` | 8123 (HTTP), **9002** (native) | Analytics |
| MinIO | `minio/minio:RELEASE.2024-12-18T13-15-44Z` | 9000 (API), 9001 (console) | Object storage |

ClickHouse **native** is mapped to host port **9002** so it does not conflict with MinIO on **9000**. Use HTTP (`8123`) for typical local DSNs — see [web/engineering/ENVIRONMENT_VARIABLES.md](../../../web/engineering/ENVIRONMENT_VARIABLES.md).

## Apply database migrations

From the repository root (with containers healthy):

```bash
make db-migrate
```

See [ADR-0005](../../../docs/adr/ADR-0005-postgres-migration-strategy.md) and `make db-version` / `make db-migrate-down` (dev rollback, one step).

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
