# Current State

**Last updated:** 2026-06-04  
**Git SHA (`main`):** `55bb33e` (M1.0.1 integration test infra [PR #43](https://github.com/Rick1330/ibex-harness/pull/43); Dependabot batch [PR #42](https://github.com/Rick1330/ibex-harness/pull/42))  
**Current phase:** Phase 1 — Core Platform  
**Current goal:** Goal 1.2 — Proxy platform integration  
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
- **Integration test infra (m1.0.1):** `infra/testing/testutil`, `make test-integration`, compose test (5433) or optional `testcontainers` build tag
- Go services:
  - `services/auth` — `/health`, `/ready`, `/metrics`, gRPC `ValidateToken`
  - `services/proxy` — `/health`, `/ready` (Redis PING if `REDIS_URL` set), `/metrics`
- Root Go module: `github.com/Rick1330/ibex-harness` (Go **1.25.11+** per [TOOLCHAIN.md](../TOOLCHAIN.md))
- Security / quality CI: CodeQL v4, Semgrep (IBEX rules), Trivy, OSV, hard-gate `golangci-lint`, Hadolint, Bandit (skip until `services/memory`)
- Informational CI: `scorecard`, `sbom` (Syft + Grype table/JSON artifacts only), `dependency-review`, `go-services`, `db-migrate-smoke`, `proto-contract`, `auth-validate-smoke`, `buf-lint`
- StepSecurity hardening ([PR #33](https://github.com/Rick1330/ibex-harness/pull/33)): Harden-Runner (audit egress), pinned GitHub Action SHAs, Docker Dependabot
- **Roadmap:** remaining planned milestones 1.1.4–1.1.6, 1.2.3–1.2.4 (docs only)
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
2. **Goal 1.1 backlog** — Token management API (1.1.4), permission bitmap ADR (1.1.5), Argon2id policy ADR (1.1.6)
3. **Proxy platform** — Input validation envelope (1.2.3), rate limit skeleton (1.2.4) after 1.2.1

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
make compose-test-up
make test-integration

IBEX_PORT=8081 IBEX_GRPC_PORT=9091 \
  POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable \
  go run ./services/auth/cmd/auth
curl -s http://localhost:8081/health
curl -s http://localhost:8081/ready
```

Expected: `/health` → `{"status":"ok"}`; `/ready` → 200 when Postgres is reachable; integration tests pass with compose test or CI Postgres.
