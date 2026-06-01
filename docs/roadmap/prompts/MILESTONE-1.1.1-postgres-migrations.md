# Milestone 1.1.1 — Execution Prompt: Postgres Migrations

Copy this prompt into your AI tool (Cursor, Codex, etc.) to implement the milestone. Do not add agent attribution to commits or PRs.

---

You are acting as **Principal Engineer + Foundation Builder** for IBEX Harness.

## Mission

Implement **Milestone 1.1.1: Postgres Migration System** as defined in [../phase-1-core-platform/milestones/1.1.1-postgres-migrations.md](../phase-1-core-platform/milestones/1.1.1-postgres-migrations.md).

## You MUST read first

- [AGENTS.md](../../../AGENTS.md)
- [.cursorrules](../../../.cursorrules)
- [docs/DATABASE_SCHEMA.md](../../DATABASE_SCHEMA.md) — `ibex_core.organizations`, `ibex_core.tokens` subsets only
- [docs/SECURITY.md](../../SECURITY.md) — RLS, fail closed, no secrets in logs
- [docs/TESTING_STRATEGY.md](../../TESTING_STRATEGY.md) — integration tests for Postgres/RLS; no RLS mocks
- [docs/FILE_STRUCTURE.md](../../FILE_STRUCTURE.md) — `infra/migrations/`, scripts layout
- [docs/ENVIRONMENT_VARIABLES.md](../../ENVIRONMENT_VARIABLES.md)
- [docs/adr/ADR-0004-protobuf-and-codegen-policy.md](../../adr/ADR-0004-protobuf-and-codegen-policy.md) (pattern for ADRs)
- [infra/compose/dev/README.md](../../../infra/compose/dev/README.md)
- [prompts/00-invariants.txt](../../../prompts/00-invariants.txt)

If any file is inaccessible, STOP and ask for it.

## Non-negotiable constraints

- **No product logic** beyond running migrations (no auth ValidateToken, no proxy routes).
- **PR-only workflow** to `main`; required CI: `repo-guards`, `markdownlint`, `gitleaks`.
- **Tenant isolation:** RLS on tenant tables; migrations must enable policies consistent with DATABASE_SCHEMA.md.
- **Minimal schema:** `organizations` + `tokens` only for this milestone — do not implement full schema.
- **No committed secrets**; use `.env.example` patterns only.
- **No agent attribution** in commits or PR description (no Co-authored-by agent trailers).

## Branch

`chore/m1-1-1-postgres-migrations`

## PR title (example)

`chore(db): postgres migrations (m1.1.1)`

## Deliverables

1. **ADR-0005** — migration tool (recommend golang-migrate), directory layout, CI advisory policy, rollback rules.
2. **`infra/migrations/postgres/`** — up/down SQL for schemas, organizations, tokens, RLS.
3. **`infra/scripts/db-migrate.sh`** — `up`, `down` (one step), `version`; bash-safe for Windows Git Bash.
4. **`infra/scripts/dev-tool.sh` + Makefile** — targets: `db-migrate`, `db-migrate-down`, `db-version`.
5. **Tests** — integration test with real Postgres (compose); idempotent second `up`; cross-tenant RLS smoke.
6. **Docs** — update DATABASE_SCHEMA.md (note migration path), DEVELOPMENT_GUIDE.md, ENVIRONMENT_VARIABLES.md, adr/README.md.
7. **CI (advisory)** — optional job: migrate against Postgres service (do not add to branch protection).

## Definition of done

- `make compose-dev-up && make db-migrate` succeeds on fresh volume.
- Second `make db-migrate` is a no-op.
- Schema matches documented subset for orgs + tokens.
- RLS enforced; test demonstrates fail closed without org context.
- All required CI checks pass.

## Output format

1. Short implementation plan (files + order).
2. Implement via PR-sized commits.
3. PR description using repo template sections: What/Why, How, Testing, Security, Docs.
4. List verification commands with expected results.
5. Risks/assumptions.

## After merge

Update [docs/roadmap/CURRENT_STATE.md](../CURRENT_STATE.md): SHA, mark 1.1.1 complete, next milestone 1.1.2.

---

*Reference: [roadmap README](../README.md)*
