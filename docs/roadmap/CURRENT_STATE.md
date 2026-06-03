# Current State

**Last updated:** 2026-06-03  
**Git SHA (`main`):** `3fcf75f`  
**Current phase:** Phase 1 — Core Platform  
**Current goal:** Goal 1.1 — Persistence and auth data plane  
**Next milestone:** [1.1.2 Auth protobuf and codegen](phase-1-core-platform/milestones/1.1.2-auth-proto-and-codegen.md)

---

## What works now

- Repository governance: PR-only `main`, required CI (`repo-guards`, `markdownlint`, `gitleaks`)
- Documentation corpus under `docs/` (architecture, schema, APIs, security, testing)
- Local toolchain: `Makefile`, `infra/scripts/dev-tool.sh`, [TOOLCHAIN.md](../TOOLCHAIN.md), optional pre-commit
- Docker Compose dev stack: Postgres (pgvector), Redis, ClickHouse, MinIO
- Protobuf source: `packages/proto` (`ContextAssemblyService`); Buf lint/breaking in CI; generated code not committed
- **Postgres migrations (m1.1.1):** `make db-migrate` applies `ibex_core.organizations` + `ibex_core.tokens` with RLS ([ADR-0005](../adr/ADR-0005-postgres-migration-strategy.md))
- Go services (skeletons):
  - `services/auth` — `/health`, `/ready` (Postgres TCP if `POSTGRES_DSN` set), `/metrics`
  - `services/proxy` — `/health`, `/ready` (Redis PING if `REDIS_URL` set), `/metrics`
- Root Go module: `github.com/Rick1330/ibex-harness` (Go **1.22+**)
- Advisory CI: `go-services`, `golangci-lint`, `db-migrate-smoke` (not branch protection)
- README: [DeepWiki](https://deepwiki.com/Rick1330/ibex-harness) badge

## What does NOT work yet

- Auth token validation, JWT issuance, permission enforcement
- Auth gRPC contract (`ibex.auth.v1`) — next in 1.1.2
- Proxy LLM forwarding, rate limiting, context injection
- gRPC between proxy and auth (blocked on 1.1.2 + 1.1.3)
- Python services: memory, context assembly, embedder, worker, API, dashboard
- Background jobs (Celery), ClickHouse trace ingestion, MinIO session archives
- OpenTelemetry exporters; official Prometheus client libraries in services
- `make db-seed` (dev seed data — future milestone)

## Next 3 immediate tasks

1. **Milestone 1.1.2** — Auth protobuf (`ibex.auth.v1`) + local codegen docs / optional `make proto-gen`
2. **Milestone 1.1.3** — Auth service: validate PAT against Postgres (fail-closed)
3. **Milestone 1.2.1** — Proxy auth gRPC client + middleware

## Verify current state locally

```bash
make help
make repo-guards
make compose-dev-up
make db-migrate
make db-version          # expect version=4 dirty=false
go test ./...
go test -tags=integration ./infra/migrations/postgres/...
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
