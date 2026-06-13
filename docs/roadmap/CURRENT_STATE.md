# Current State

**Last updated:** 2026-06-13  
**Git SHA (`main`):** `f4ef55f` — D.3.2 wave 2 (#121)  
**Current phase:** Phase 1.5 — Docs Site (**In progress**)  
**Current goal:** Wave 7 — [D.3.2](phase-1-5-docs-site/milestones/d3.2-seed-pages-content-stubs.md) seed content (Deployment section next)  
**Next backend milestone (blocked):** [2.1.1 Provider interface and registry](phase-2-single-provider/milestones/2.1.1-provider-interface-and-registry.md) — after Phase 1.5 launch  
**Phase 1 exit audit:** [PHASE1_EXIT_AUDIT.md](phase-1-core-platform/PHASE1_EXIT_AUDIT.md)  
**CI audit:** [CI_AUDIT.md](phase-1-core-platform/CI_AUDIT.md)

---

## What works now

- Repository governance: PR-only `main`, required CI ([ADR-0008](../adr/ADR-0008-security-ci-gates.md)): `repo-guards`, `markdownlint`, `gitleaks`, `CodeQL`, `trivy`, `osv-scan`, `semgrep`, `golangci-lint`, `coverage`, `CodeScene Code Health Review (main)`, `security-integration`, `go-race`, `go-services (auth)`, `go-services (proxy)`, `proxy-auth-smoke`, `bandit`, `hadolint`
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
- **Shared structured logger (m1.3.3):** `packages/logger` mandatory JSON schema; adopted in auth/proxy via DI
- **OTel tracer and meter providers (m1.3.1):** `packages/telemetry` ([ADR-0019](../adr/ADR-0019-opentelemetry-provider-configuration.md))
- **Prometheus metric catalog (m1.3.2):** `packages/metrics` ([ADR-0021](../adr/ADR-0021-prometheus-metric-catalog.md))
- **Developer experience baseline (m1.4.1):** `make db-seed`, `make dev-smoke`, enhanced `.env.example` files
- **Shared config and error packages (m1.4.2):** `packages/config`, `packages/apierror` ([ADR-0020](../adr/ADR-0020-shared-package-boundaries.md))
- **Health check contract (m1.4.3):** `packages/healthcheck` ([ADR-0022](../adr/ADR-0022-health-check-contract.md)); [OPS_GUIDE.md](../OPS_GUIDE.md)
- **Security integration gate (m1.5.1+):** 35+ SEC cases in `services/proxy/proxy_security_sec*_test.go` (path org, Redis fail-open, envelope sweep); CI `security-integration` with `-list` guard; [SECURITY.md](../SECURITY.md) Appendix A
- **Handwritten coverage gate (#92):** merged unit+integration Go coverage ≥80% on hand-written code (`packages/proto/gen/go` excluded); enforced by CI `coverage` job via `infra/scripts/coverage-gate.sh`; see [CI_AUDIT.md](phase-1-core-platform/CI_AUDIT.md) and [COVERAGE_GAP_REGISTER.md](phase-1-core-platform/COVERAGE_GAP_REGISTER.md)
- **Trunk Flaky Tests (#94):** all Go CI test jobs emit JUnit via gotestsum and upload to Trunk (`ibexharness` org); per-job variants; informational only (`continue-on-error`); see [CI_AUDIT.md](phase-1-core-platform/CI_AUDIT.md) § Trunk
- **Landing + DNS (pre–Phase 1.5):** `ibexharness.com` live ([marvel-scape](https://github.com/Rick1330/marvel-scape)); Cloudflare `docs` CNAME ready for `docs.ibexharness.com` — see [Phase 1.5 roadmap](phase-1-5-docs-site/README.md)
- **Phase 1.5 Wave 0 (#96):** roadmap scaffold, ADR-0023, 21 milestone specs, `MASTER_BRIEF.md`, repo-guards allows `docs/app/` + pnpm root files
- **Phase 1.5 D.1.1 (#98):** pnpm + Turborepo at repo root; public site at `docs/app/`
- **Phase 1.5 D.1.2 (#100):** `.cursor/rules/docs-site.mdc`, `.nvmrc`, `docs/app/CONTRIBUTING.md`
- **Phase 1.5 D.2.1 (#101):** Fumadocs v14 + Next.js 15; introduction seed page; `pnpm docs:build` passes
- **Phase 1.5 hotfix (#103):** `globals.css` — Fumadocs `@import` before Tailwind directives (Turbopack parse fix)
- **Phase 1.5 D.2.2 (#104):** Matte Graphite tokens, dark default, IBEX/HARNESS wordmark — **design review gate** (375/768/1440) before D.2.3+
- **Phase 1.5 D.2.7 (#106):** Sidebar, breadcrumbs, on-this-page rail, Edit-on-GitHub + last-updated footer
- **Phase 1.5 D.2.3 (#108):** MDX kit — Callout, Steps, CodeTabs, Endpoint, Badge, Kbd; showcase at `_design/components`
- **Phase 1.5 D.2.4–D.3.1 (#114):** Dynamic OG images, Cmd+K search, enhanced code blocks (Shiki + copy), styled 404, IA skeleton (26 routes), dev perf (Zod v4, webpack default)
- **Phase 1.5 perf (#116):** Static doc pages; subtle article fade (layout-safe)
- **Phase 1.5 layout hotfix (#119):** Restored 3-column Fumadocs shell after flex-breaking wrapper regression
- **Phase 1.5 D.3.2 wave 1 (#117):** Getting Started content — introduction, concepts, FAQ, quickstart stubs with Callout, Steps, runnable snippets
- **Phase 1.5 D.3.2 wave 2 (#121):** Proxy + Auth content — 10 pages with Callout/Steps, curl examples, Phase 1 honesty on stubbed provider paths
- **Codecov:** Go coverage upload; badge in README; patch/project thresholds aligned to 80% handwritten scope
- **Integration test infra (m1.0.1):** `infra/testing/testutil`, `make test-integration`, compose test (5433) or optional `testcontainers` build tag
- Go services:
  - `services/auth` — `/health`, `/ready`, `/metrics`, gRPC `ValidateToken` + `ValidateAgent`
  - `services/proxy` — auth + agent verify + rate limit on `/v1/*`; stable error envelope on JSON errors
- Root Go module: `github.com/Rick1330/ibex-harness` (Go **1.25.11+** per [TOOLCHAIN.md](../TOOLCHAIN.md))
- Security / quality CI: CodeQL v4, Semgrep (IBEX rules), Trivy, OSV, hard-gate `golangci-lint` (packages + services), `security-integration`, `go-race`, Hadolint, Bandit (skip until `services/memory`)
- Informational CI: `scorecard`, `sbom`, `dependency-review`, `db-migrate-smoke`, `proto-contract`, `auth-validate-smoke`, `proxy-agent-verify-smoke`, `buf-lint`, `codecov/patch`
- README: slim front door with CI + CodeScene badges; [CODE_OF_CONDUCT.md](../../CODE_OF_CONDUCT.md); [.github/SUPPORT.md](../../.github/SUPPORT.md)

## What does NOT work yet

- JWT issuance, dashboard session flows
- Proxy LLM forwarding, context injection
- Python services: memory, context assembly, embedder, worker, API, dashboard
- Background jobs (Celery), ClickHouse trace ingestion, MinIO session archives

## Next 3 immediate tasks

1. **Phase 1.5 Wave 7 — D.3.2 wave 3** — Deployment content section (`feat/d3-2-deployment`)
2. **Phase 1.5 Wave 9 — D.3.3** — Five-minute quickstart polish (`feat/d3-3-quickstart`)
3. **Phase 2 blocked** — [2.1.1](phase-2-single-provider/milestones/2.1.1-provider-interface-and-registry.md) until Phase 1.5 launch (Wave 12)

## Verify current state locally

```bash
make help
make repo-guards
make compose-dev-up
make db-migrate
make db-seed
make proto-gen
go test ./packages/...
go test ./services/proxy/...
make compose-test-up
go test -tags=integration -run '^TestSecurity_' ./services/proxy
make test-integration
pnpm install
pnpm docs:dev
```

Windows: see [services/auth/README.md](../../services/auth/README.md) and [services/proxy/README.md](../../services/proxy/README.md) for PowerShell env syntax. Integration tests: `make compose-test-up` (Postgres 5433) or `$env:POSTGRES_TEST_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"` for dev Postgres.

Expected: `security-integration` green in CI; all proxy integration tests pass with `compose-test-up`.
