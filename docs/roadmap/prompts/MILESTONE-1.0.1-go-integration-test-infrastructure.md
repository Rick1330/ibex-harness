# Milestone 1.0.1 — Execution Prompt: Go Integration Test Infrastructure

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Test Owner** for IBEX Harness.

## Mission

Implement **Milestone 1.0.1: Go Integration Test Infrastructure** as defined in [../phase-1-core-platform/milestones/1.0.1-go-integration-test-infrastructure.md](../phase-1-core-platform/milestones/1.0.1-go-integration-test-infrastructure.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md)
- [.cursorrules](../../../.cursorrules)
- [docs/TESTING_STRATEGY.md](../../TESTING_STRATEGY.md) — §4 integration, §6.2 auth
- [docs/DEVELOPMENT_GUIDE.md](../../DEVELOPMENT_GUIDE.md)
- [docs/ENVIRONMENT_VARIABLES.md](../../ENVIRONMENT_VARIABLES.md)
- [docs/adr/ADR-0005-postgres-migration-strategy.md](../../adr/ADR-0005-postgres-migration-strategy.md)
- [docs/adr/ADR-0007-auth-token-validation.md](../../adr/ADR-0007-auth-token-validation.md)
- [infra/compose/test/docker-compose.yml](../../../infra/compose/test/docker-compose.yml)
- [services/auth/validate_integration_test.go](../../../services/auth/validate_integration_test.go)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

If any file is inaccessible, STOP and ask for it.

## Non-negotiable constraints

- **No RLS mocking** — integration tests use real Postgres + `app.current_org_id` / `app.is_service_account`
- **`//go:build integration`** on integration test files; default `go test ./...` stays unit-only
- **Never log or commit raw PAT secrets** in fixtures
- **Do not import `services/*/internal/*` from `infra/testing/testutil`** (Go internal visibility)
- **CI unchanged** — keep `auth-validate-smoke` on GHA Postgres; testcontainers local-only unless explicitly requested
- **PR-only** to `main`; required CI: `repo-guards`, `markdownlint`, `gitleaks`, `CodeQL`, `trivy`, `osv-scan`, `semgrep`, `golangci-lint`, `bandit`, `hadolint`
- **No agent attribution** in commits or PR description

## Branch

`chore/m1-0-1-integration-test-infra`

## PR title

`chore(test): Go integration test infrastructure (m1.0.1)`

## Deliverables

1. `infra/testing/testutil` — `SetupPostgres`, `OpenDB`, `WithServiceAccount`, `WithAppRole`, `MustSetOrgContext`, `SeedOrganization`, `SeedToken`, RLS smoke test
2. `go.mod` — testcontainers-go (+ postgres/redis modules); `docs/DEPENDENCIES.md` admission
3. `make test-integration` — `go test -tags=integration -race -timeout=120s ./...`
4. Auth integration tests refactored to `testutil.SetupPostgres`
5. `DEVELOPMENT_GUIDE.md` — compose test vs `IBEX_USE_TESTCONTAINERS=1`
6. `decisions.md` row for CI service containers vs local testcontainers

## Definition of done

- `make test-integration` documented and works with compose test stack
- `IBEX_USE_TESTCONTAINERS=1 go test -tags="integration testcontainers" ./infra/testing/testutil/...` passes with Docker
- Auth integration tests pass in CI (`auth-validate-smoke`) without testcontainers
- Required CI green

## Verification commands

```bash
make compose-test-up
make test-integration
go test ./...

# Optional (Docker required):
IBEX_USE_TESTCONTAINERS=1 go test -tags="integration testcontainers" ./infra/testing/testutil/...
IBEX_USE_TESTCONTAINERS=1 go test -tags="integration testcontainers" ./services/auth/...

make repo-guards lint-docs
```

## After merge

Update [docs/roadmap/CURRENT_STATE.md](../CURRENT_STATE.md): SHA, 1.0.1 complete, next 1.2.1.

---

*Reference: [roadmap README](../README.md)*
