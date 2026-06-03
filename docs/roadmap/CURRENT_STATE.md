# Current State

**Last updated:** 2026-06-03  
**Git SHA (`main`):** `c939d75` (security CI + post-merge follow-up [PR #31](https://github.com/Rick1330/ibex-harness/pull/31))  
**Current phase:** Phase 1 — Core Platform  
**Current goal:** Goal 1.1 — Persistence and auth data plane  
**Next milestone:** [1.2.1 Proxy auth client](phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md)

---

## What works now

- Repository governance: PR-only `main`, required CI ([ADR-0008](../adr/ADR-0008-security-ci-gates.md)): `repo-guards`, `markdownlint`, `gitleaks`, `CodeQL`, `trivy`, `osv-scan`, `semgrep`, `golangci-lint`, `bandit`, `hadolint`
- Documentation corpus under `docs/` (architecture, schema, APIs, security, testing)
- Local toolchain: `Makefile`, `infra/scripts/dev-tool.sh`, [TOOLCHAIN.md](../TOOLCHAIN.md), optional pre-commit
- Docker Compose dev stack: Postgres (pgvector), Redis, ClickHouse, MinIO
- Protobuf source: `packages/proto` (`ContextAssemblyService`, `AuthService.ValidateToken`); Buf lint/breaking in CI; generated code not committed
- **Postgres migrations (m1.1.1):** `make db-migrate` applies `ibex_core.organizations` + `ibex_core.tokens` with RLS ([ADR-0005](../adr/ADR-0005-postgres-migration-strategy.md))
- **Auth protobuf (m1.1.2):** `ibex.auth.v1` + ADR-0006; `make proto-gen`, `make proto-test`, `make proto-test-integration`; CI `proto-contract` job
- **Auth ValidateToken (m1.1.3):** gRPC server on `IBEX_GRPC_PORT` (default 9091); PAT parse + Argon2id + Postgres lookup ([ADR-0007](../adr/ADR-0007-auth-token-validation.md)); CI `auth-validate-smoke`
- Go services:
  - `services/auth` — `/health`, `/ready`, `/metrics`, gRPC `ValidateToken`
  - `services/proxy` — `/health`, `/ready` (Redis PING if `REDIS_URL` set), `/metrics`
- Root Go module: `github.com/Rick1330/ibex-harness` (Go **1.25.11+** per [TOOLCHAIN.md](../TOOLCHAIN.md))
- Security / quality CI: CodeQL, Semgrep (IBEX rules), Trivy, OSV, hard-gate `golangci-lint`, Hadolint, Bandit (skip until `services/memory`)
- Informational CI: `scorecard`, `sbom` (Syft + Grype artifacts), `go-services`, `db-migrate-smoke`, `proto-contract`, `auth-validate-smoke`, `buf-lint`
- README: [DeepWiki](https://deepwiki.com/Rick1330/ibex-harness) badge
- Semgrep: Prometheus `/metrics` handlers use `strings.Builder` (no Fprintf to ResponseWriter)

## What does NOT work yet

- Proxy auth gRPC client + middleware (1.2.1)
- JWT issuance, dashboard session flows
- Proxy LLM forwarding, rate limiting, context injection
- Python services: memory, context assembly, embedder, worker, API, dashboard
- Background jobs (Celery), ClickHouse trace ingestion, MinIO session archives
- OpenTelemetry exporters; official Prometheus client libraries in services
- `make db-seed` (dev seed data — future milestone)

## Next 3 immediate tasks

1. **Milestone 1.2.1** — Proxy auth gRPC client + middleware
2. **Milestone 1.2.2** — Proxy LLM forwarding (if sequenced after auth client)
3. **Goal 1.1 completion** — review remaining 1.1 milestones in roadmap

## Verify current state locally

```bash
make help
make repo-guards
make compose-dev-up
make db-migrate
make db-version          # expect version=4 dirty=false
make proto-gen
make proto-test
go test ./services/auth/...
go test -tags=integration ./services/auth/...

IBEX_PORT=8081 IBEX_GRPC_PORT=9091 \
  POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable \
  go run ./services/auth/cmd/auth
curl -s http://localhost:8081/health
curl -s http://localhost:8081/ready

# After seeding a PAT (see services/auth README / integration tests):
# grpcurl -plaintext -d '{"access_token":"ibex_pat_<uuid>_<secret>"}' \
#   localhost:9091 ibex.auth.v1.AuthService/ValidateToken
```

Expected: `/health` → `{"status":"ok"}`; `/ready` → 200 when Postgres is reachable; ValidateToken returns `OK` for a valid seeded PAT.
