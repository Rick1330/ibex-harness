# Current State

**Last updated:** 2026-06-05  
**Git SHA (`main`):** `d366743` — M1.4.3 health check contract ([#85](https://github.com/Rick1330/ibex-harness/pull/85))  
**Current phase:** Phase 1 — Core Platform  
**Current goal:** Goal 1.5 — Phase 1 security gate  
**Next milestone:** [1.5.1 Security integration test suite](phase-1-core-platform/milestones/1.5.1-security-integration-test-suite.md)

---

## What works now

- Repository governance: PR-only `main`, required CI ([ADR-0008](../adr/ADR-0008-security-ci-gates.md)): `repo-guards`, `markdownlint`, `gitleaks`, `CodeQL`, `trivy`, `osv-scan`, `semgrep`, `golangci-lint`, `bandit`, `hadolint`
- Documentation corpus under `docs/` (architecture, schema, APIs, security, testing)
- Local toolchain: `Makefile`, `infra/scripts/dev-tool.sh`, [TOOLCHAIN.md](../TOOLCHAIN.md), optional pre-commit
- Docker Compose dev stack: Postgres (pgvector), Redis, ClickHouse, MinIO
- Protobuf source: `packages/proto` (`ContextAssemblyService`, `AuthService.ValidateToken`); Buf lint/breaking in CI; generated code not committed
- **Postgres migrations (m1.1.1):** `make db-migrate` applies `ibex_core.organizations` + `ibex_core.tokens` with RLS ([ADR-0005](../adr/ADR-0005-postgres-migration-strategy.md))
- **Users and agents schema (m1.1.7):** `ibex_core.users` + `ibex_core.agents` (Phase-1 subset); token FKs on `user_id`/`agent_id`/`revoked_by`; `ValidateAgent` gRPC ([ADR-0014](../adr/ADR-0014-core-domain-migration-sequencing.md))
- **Auth protobuf (m1.1.2):** `ibex.auth.v1` + ADR-0006; `make proto-gen`, `make proto-test`, `make proto-test-integration`; CI `proto-contract` job
- **Auth ValidateToken (m1.1.3):** gRPC server on `IBEX_GRPC_PORT` (default 9091); PAT parse + Argon2id + Postgres lookup ([ADR-0007](../adr/ADR-0007-auth-token-validation.md)); CI `auth-validate-smoke`
- **Permission bitmap (m1.1.5):** `packages/permissions`, [ADR-0009](../adr/ADR-0009-permission-bitmap.md)
- **Token management (m1.1.4):** gRPC `CreateToken`, `RevokeToken`, `ListTokens`; caller bearer authz; `GeneratePAT` per ADR-0007
- **Crypto policy (m1.1.6):** `packages/crypto`, [ADR-0010](../adr/ADR-0010-cryptography-policy.md) (Argon2id PHC, production p=4)
- **Proxy auth client (m1.2.1):** gRPC ValidateToken middleware, protected probe routes ([ADR-0011](../adr/ADR-0011-proxy-auth-client.md))
- **Proxy request normalization (m1.2.2):** OpenAI chat JSON parse; `INVALID_JSON` / `501 PROVIDER_NOT_CONFIGURED` ([ADR-0012](../adr/ADR-0012-proxy-request-normalization.md))
- **Proxy input validation (m1.2.3):** body limit, Content-Type, semantic `field_errors`, response headers, `X-IBEX-Agent-ID` ([ADR-0013](../adr/ADR-0013-proxy-input-validation-and-error-envelope.md))
- **Proxy rate limit skeleton (m1.2.4):** `packages/ratelimit`, org-level Redis RPM, fail-open, 429 `RATE_LIMITED` ([ADR-0015](../adr/ADR-0015-proxy-rate-limit-skeleton.md))
- **Proxy agent identity verification (m1.2.5):** `ValidateAgent` middleware, required `X-IBEX-Agent-ID`, fail-closed, 403/503 agent errors ([ADR-0016](../adr/ADR-0016-agent-identity-verification.md))
- **Request ID correlation (m1.2.6):** `packages/reqid` UUID v7, inbound validation, gRPC `x-request-id` to auth ([ADR-0017](../adr/ADR-0017-request-id-strategy.md))
- **Graceful shutdown (m1.2.7):** `packages/shutdown` coordinator, SIGTERM drain / SIGINT immediate, `IBEX_SHUTDOWN_TIMEOUT` ([ADR-0018](../adr/ADR-0018-graceful-shutdown.md))
- **Shared structured logger (m1.3.3):** `packages/logger` mandatory JSON schema (`timestamp`, `level`, `message`, `service`, `request_id`, `trace_id`); forbidden-field redaction; adopted in auth/proxy via DI; `packages/shutdown` uses `*logger.Logger`; per-request access logs at DEBUG
- **OTel tracer and meter providers (m1.3.1):** `packages/telemetry` Init with OTLP gRPC or noop exporters; W3C trace context propagator; HTTP `SpanMiddleware` on auth/proxy; `X-Trace-ID` from OTel span (synthetic UUID retired); gRPC client trace propagation via `otelgrpc`; shutdown hook registered first ([ADR-0019](../adr/ADR-0019-opentelemetry-provider-configuration.md))
- **Prometheus metric catalog (m1.3.2):** `packages/metrics` canonical registry; `prometheus/client_golang` on auth/proxy; Phase 1 catalog (proxy HTTP, auth gRPC/HTTP/DB, rate-limit, process_up); route-template labels; proxy middleware order `RequestContext → Span → metrics → …` ([ADR-0021](../adr/ADR-0021-prometheus-metric-catalog.md))
- **Developer experience baseline (m1.4.1):** `make db-seed` (idempotent fixed-UUID dev org/user/agent/PAT); `make dev-smoke` (7 local HTTP checks, 501 stub); `infra/tools/hashtoken`; enhanced auth/proxy `.env.example`; README quick-start path; local dev follow-up `compose-dev-reset`, `db-repair-token-fks`, Windows docker psql seed ([#79](https://github.com/Rick1330/ibex-harness/pull/79))
- **Shared config and error packages (m1.4.2):** `packages/config` typed env load (`caarlos0/env/v11`); `packages/apierror` canonical codes + ADR-0013 envelope; adopted in auth/proxy ([ADR-0020](../adr/ADR-0020-shared-package-boundaries.md)) ([#82](https://github.com/Rick1330/ibex-harness/pull/82))
- **Health check contract (m1.4.3):** `packages/healthcheck` shared `/health` + `/ready`; auth checks postgres + grpc; proxy checks auth_grpc + redis ([ADR-0022](../adr/ADR-0022-health-check-contract.md)); [OPS_GUIDE.md](../OPS_GUIDE.md)
- **Integration test infra (m1.0.1):** `infra/testing/testutil`, `make test-integration`, compose test (5433) or optional `testcontainers` build tag
- Go services:
  - `services/auth` — `/health`, `/ready`, `/metrics`, gRPC `ValidateToken` + `ValidateAgent`
  - `services/proxy` — auth + agent verify + rate limit on `/v1/*`; stable error envelope on JSON errors
- Root Go module: `github.com/Rick1330/ibex-harness` (Go **1.25.11+** per [TOOLCHAIN.md](../TOOLCHAIN.md))
- Security / quality CI: CodeQL v4, Semgrep (IBEX rules), Trivy, OSV, hard-gate `golangci-lint`, Hadolint, Bandit (skip until `services/memory`)
- Informational CI: `scorecard`, `sbom` (Syft + Grype table/JSON artifacts only), `dependency-review`, `go-services`, `db-migrate-smoke`, `proto-contract`, `auth-validate-smoke`, `proxy-auth-smoke`, `proxy-agent-verify-smoke`, `buf-lint`
- StepSecurity hardening ([PR #33](https://github.com/Rick1330/ibex-harness/pull/33)): Harden-Runner (audit egress), pinned GitHub Action SHAs, Docker Dependabot
- **Cursor rules (PR #59):** `.cursorrules` registry + `.cursor/rules/00–29.mdc`; markdownlint covers `*.mdc`
- **Roadmap (PR #59):** Phase 1 milestones 1.4.1–1.4.3, 1.5.1 documented; Phase 2 full milestone tree (2.1.1–2.6.2) in [phase-2-single-provider/](phase-2-single-provider/README.md); `PHASE1_GAP_ANALYSIS.md` retired
- **Roadmap execution:** next milestones 1.3.2 → 1.4.1 → … → 1.5.1 (see [phase-1 README](phase-1-core-platform/README.md#execution-order))
- README: slim front door with CI + [CodeScene](https://codescene.io/projects/80943) badges, honest Phase 1 status; [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md) (Contributor Covenant 2.1); [.github/SUPPORT.md](../../.github/SUPPORT.md)
- Semgrep: Prometheus `/metrics` handlers use `strings.Builder` (no Fprintf to ResponseWriter)

## What does NOT work yet

- JWT issuance, dashboard session flows
- Proxy LLM forwarding, context injection
- Python services: memory, context assembly, embedder, worker, API, dashboard
- Background jobs (Celery), ClickHouse trace ingestion, MinIO session archives

## Next 3 immediate tasks

1. **Milestone 1.5.1** — Security integration test suite
2. **Phase 2 prep** — review [phase-2 README](phase-2-single-provider/README.md)

## Verify current state locally

```bash
make help
make repo-guards
make compose-dev-up
make db-migrate
make db-seed
make proto-gen
go test ./packages/logger/...
go test ./packages/telemetry/...
go test ./packages/shutdown/...
go test ./packages/ratelimit/...
go test ./packages/metrics/...
go test ./packages/config/...
go test ./packages/apierror/...
go test ./packages/healthcheck/...
go test ./services/proxy/...
make compose-test-up
make test-integration
```

Windows: see [services/auth/README.md](../../services/auth/README.md) and [services/proxy/README.md](../../services/proxy/README.md) for PowerShell env syntax (`$env:VAR = "..."`). Integration tests on dev Postgres: `$env:POSTGRES_TEST_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"`.

Expected: `proxy-auth-smoke` green in CI; local integration tests pass with `compose-test-up` (5433) or `POSTGRES_TEST_DSN` pointing at dev Postgres (5432).
