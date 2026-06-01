# Current State

**Last updated:** 2026-06-01  
**Git SHA (`main`):** `5d0bfac`  
**Current phase:** Phase 1 — Core Platform  
**Current goal:** Goal 1.1 — Persistence and auth data plane  
**Next milestone:** [1.1.1 Postgres migrations](phase-1-core-platform/milestones/1.1.1-postgres-migrations.md)

---

## What works now

- Repository governance: PR-only `main`, required CI (`repo-guards`, `markdownlint`, `gitleaks`)
- Documentation corpus under `docs/` (architecture, schema, APIs, security, testing)
- Local toolchain: `Makefile`, `infra/scripts/dev-tool.sh`, [TOOLCHAIN.md](../TOOLCHAIN.md), optional pre-commit
- Docker Compose dev stack: Postgres (pgvector), Redis, ClickHouse, MinIO
- Protobuf source: `packages/proto` (`ContextAssemblyService`); Buf lint/breaking in CI; generated code not committed
- Go services (skeletons):
  - `services/auth` — `/health`, `/ready` (Postgres TCP if `POSTGRES_DSN` set), `/metrics`
  - `services/proxy` — `/health`, `/ready` (Redis PING if `REDIS_URL` set), `/metrics`
- Root Go module: `github.com/Rick1330/ibex-harness`
- Advisory CI: `go-services`, `golangci-lint` (not branch protection)

## What does NOT work yet

- Postgres schema migrations or RLS applied in dev
- Auth token validation, JWT issuance, permission enforcement
- Proxy LLM forwarding, rate limiting, context injection
- gRPC between proxy and auth (no auth proto yet)
- Python services: memory, context assembly, embedder, worker, API, dashboard
- Background jobs (Celery), ClickHouse trace ingestion, MinIO session archives
- OpenTelemetry exporters; official Prometheus client libraries in services

## Next 3 immediate tasks

1. **Milestone 1.1.1** — Postgres migration system + minimal `ibex_core` schema (orgs, tokens subset)
2. **Milestone 1.1.2** — Auth protobuf package + local/CI codegen policy
3. **Milestone 1.1.3** — Auth service: validate PAT against Postgres (fail-closed)

## Verify current state locally

```bash
make help
make repo-guards
make compose-dev-up
make compose-dev-ps
go test ./...
go build -o /tmp/auth ./services/auth/cmd/auth
go build -o /tmp/proxy ./services/proxy/cmd/proxy

# Auth (requires POSTGRES_DSN; compose provides Postgres)
IBEX_PORT=8081 POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex go run ./services/auth/cmd/auth
curl -s http://localhost:8081/health
curl -s http://localhost:8081/ready

# Proxy (requires REDIS_URL)
IBEX_PORT=8080 REDIS_URL=redis://localhost:6379/0 go run ./services/proxy/cmd/proxy
curl -s http://localhost:8080/health
curl -s http://localhost:8080/ready
```

Expected: `/health` → `{"status":"ok"}`; `/ready` → 200 when dependency env is set and compose is healthy, else 503 with JSON reason.
