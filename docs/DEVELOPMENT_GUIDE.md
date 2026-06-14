# IBEX Harness — Development Guide

## 1) Purpose

This document defines **how we build IBEX Harness** so that:

- The codebase stays coherent across many services and languages
- AI-assisted development remains reliable (no drift, no hallucinated APIs, no framework violations)
- Quality is enforced automatically (lint/typecheck/tests/security) and culturally (review standards)
- Work can be executed in parallel without integration chaos

If there is any conflict between this guide and actual CI rules, **CI wins**. Update this document to match reality.

---

## 2) Operating Principles (Non‑Negotiables)

### 2.1 “Production-quality by default”

- No placeholder logic in core paths (auth, proxy, tenant isolation, storage)
- All new behavior ships with tests
- All interfaces are explicit and versioned
- All services are observable (metrics/logs/traces)

### 2.2 Defense-in-depth multi‑tenancy

Even with PostgreSQL RLS enabled:

- Every query still includes `org_id` filtering (defense in depth)
- Every Redis key is namespaced with `org_id` (or explicitly global if safe)
- Every ClickHouse query must include `org_id` (ClickHouse has no RLS)

### 2.3 Strict contract discipline

- Protobuf is the internal contract source of truth
- REST endpoints are versioned (`/v1/...`) with a stable error shape
- Any contract change requires:
  - Compatibility plan (migration, fallback)
  - Updated docs
  - Tests for the new behavior

### 2.4 “Fast critical path, async everything else”

The LLM Proxy and Context Assembly are latency-sensitive. Everything else must be designed to avoid blocking that path.

---

## 3) Repository Structure (Monorepo)

Target structure (actual may evolve, but changes must be deliberate):

```text
ibex-harness/
  services/                 # deployable services
    proxy/                  # Go
    auth/                   # Go
    api/                    # Python FastAPI (management plane)
    memory/                 # Python FastAPI (memory CRUD/search)
    context/                # Python gRPC (context assembly)
    embedder/               # Python FastAPI (embedding)
    worker/                 # Python Celery workers
    dashboard/              # Next.js (TypeScript)

  packages/                 # shared artifacts + SDKs
    proto/                  # protobuf definitions (source of truth)
    sdk-python/
    sdk-typescript/
    sdk-go/
    cli/                    # Go CLI

  infra/
    compose/                # local/dev/test compose files
    docker/                 # Dockerfiles + build assets
    k8s/                    # raw manifests (if any)
    helm/                   # Helm charts for deployment
    terraform/              # IaC
    monitoring/             # Prometheus/Grafana/Loki/Tempo configs

  docs/
    PROJECT_CONTEXT.md
    ARCHITECTURE.md
    TECH_STACK.md
    API_DOCUMENTATION.md
    DATABASE_SCHEMA.md
    CODING_STANDARDS.md
    SECURITY.md
    TESTING_STRATEGY.md
    PERFORMANCE.md
    MONITORING.md
    adr/                    # README pointer → docs/app/content/docs/adr/
```

**Rule:** Don’t invent new top-level directories casually. If you need one, justify it with an ADR.

---

## 4) Local Development (the “one hour rule”)

A new contributor should be able to get productive in **≤ 1 hour**.

### 4.1 Prerequisites

- Docker + Docker Compose
- GNU Make
- Go 1.22+
- Python 3.11+
- Node.js 18+
- Buf CLI
- Bash (Git Bash on Windows)

See [TOOLCHAIN.md](TOOLCHAIN.md) for installation instructions and sanity checks.

### 4.0 Development roadmap

Implementation progress is tracked in [`docs/app/content/roadmap/current-state.mdx`](../app/content/roadmap/current-state.mdx) (public `/roadmap/current-state` on the docs site). After every milestone merges to `main`, update that file (Git SHA, what works / does not, next three tasks). Milestone definitions live under [`docs/app/content/roadmap/phase-1-core-platform/milestones/`](../app/content/roadmap/phase-1-core-platform/milestones/). Log plan changes in [`docs/app/content/roadmap/findings.mdx`](../app/content/roadmap/findings.mdx).

**Execution prompts** for AI-assisted milestone work live in `ibex-harness-workspace/prompts/` (local workspace, not published on the docs site).

Session notes and closed audits live in the **session workspace** (sibling `ibex-harness-workspace`, not in git). See §12.

### 4.1.1 Canonical local commands

Use the root `Makefile` for common local tasks:

```bash
make help
make repo-guards
make lint-docs
make proto-lint
make compose-dev-up
```

### 4.2 Local infra

We run local dependencies via Compose:

- PostgreSQL (pgvector)
- Redis (prefer Redis Stack)
- ClickHouse
- MinIO (S3-compatible)
- (Optional) Monitoring stack

Expected command (example):

```bash
docker compose -f infra/compose/dev/docker-compose.yml up -d
```

### 4.3 Migrations and seed

After local infra is running:

```bash
make compose-dev-up
make db-migrate
```

Re-running `make db-migrate` is idempotent (no pending migrations). Roll back one step in dev only: `make db-migrate-down`. Check version: `make db-version`.

### Seed data (`make db-seed`)

After migrations, seed fixed development rows (org, user, agent, PAT):

```bash
make db-seed
```

- **Idempotent:** safe to run multiple times (`ON CONFLICT DO NOTHING`).
- **Never run against staging or production** — `db-seed` refuses non-local DSN hosts and `IBEX_ENV=production`.
- **Dev PAT (ADR-0007 wire form):** `ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY`
- **Fixed IDs:** org `...0001`, agent `...0003` (see `infra/scripts/seed_dev.sql`).
- Hash embedded in SQL is generated via `go run ./infra/tools/hashtoken <bearer>`.

### Local smoke test (`make dev-smoke`)

With Compose, migrations, seed, auth, and proxy running:

```bash
make dev-smoke
```

Checks `/health`, `/ready`, auth failures (401/400), chat stub (501 without LLM), and auth probe routes. Optional rate-limit WARN if 429 is not observed in 65 rapid requests.

Proxy must reach auth gRPC on `IBEX_AUTH_GRPC_ADDR` (default `127.0.0.1:9091`). For local dev, set `IBEX_AUTH_VALIDATE_TIMEOUT=2s` on the proxy — the default `50ms` production budget is often too low for Argon2 token verification on developer machines; without it, bearer requests return **503** `SERVICE_DEGRADED` before the missing-agent **400** check runs.

### 4.4 Run services

Recommended pattern: run infra in Docker, run services on host for fast iteration.

Example (per-service):

```bash
make dev-auth
make dev-proxy
make dev-memory
make dev-context
make dev-embedder
make dev-worker
make dev-api
make dev-dashboard
```

### 4.5 Health checks

```bash
curl -s http://localhost:8000/v1/health | jq
curl -s http://localhost:8080/health | jq
```

**Rule:** Every service must expose:

- `GET /health` (liveness; minimal dependencies)
- `GET /ready` (readiness; verifies critical dependencies)

---

## 5) Environment Configuration

### 5.1 Environment variable rules

- Use `.env.example` per service
- Never commit `.env` files
- Secrets must be injected via environment variables in dev, and via Vault/Secrets Manager in production

### 5.2 Precedence rules

1. CLI flags
2. Environment variables
3. Local `.env` file (dev only)
4. Defaults (safe defaults)

### 5.3 Required variables (typical)

- `POSTGRES_DSN`
- `REDIS_URL`
- `CLICKHOUSE_DSN`
- `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`
- `JWT_PRIVATE_KEY` (auth service), `JWT_PUBLIC_KEYS` (verifiers)
- `SENTRY_DSN` (optional in dev)

---

## 6) Branching Strategy

### 6.1 Branch names

Use:

- `feature/IBEX-1234-short-description`
- `fix/IBEX-1234-short-description`
- `perf/IBEX-1234-short-description`
- `security/IBEX-1234-short-description`
- `refactor/IBEX-1234-short-description`
- `chore/IBEX-1234-short-description`

### 6.1.1 Milestone branches (roadmap)

When implementing a milestone from [`docs/app/content/roadmap/`](../app/content/roadmap/) (public `/roadmap`), use this pattern until a GitHub issue exists:

```text
<type>/m{phase}-{goal}-{milestone}-{kebab-slug}
```

| Type | Use for |
| --- | --- |
| `chore` | Migrations, proto/codegen, observability scaffolding, docs-only roadmap |
| `feature` | Auth, proxy, or other user-visible behavior |
| `fix` / `security` | Defect or security work scoped to one milestone |

**Examples:** `chore/m1-1-1-postgres-migrations`, `feature/m1-2-1-proxy-auth-client`.

**Ticket override:** When tracked as `IBEX-####`, prefer `feature/IBEX-####-same-slug` (or `chore/` / `fix/` as appropriate) instead of the `m*` prefix.

**PR title:** Conventional commit + milestone tag, e.g. `chore(db): postgres migrations (m1.1.1)`.

**Historical:** Foundation work used `chore/foundation-00N-*` without ticket IDs; do not reuse that pattern for Phase 1+ milestones.

One milestone per branch (see §6.2). Branch names and PR titles for each milestone are listed in the milestone file under `docs/app/content/roadmap/`.

### 6.2 Branch scope rule (AI-friendly)

A branch should correspond to **one coherent unit of change**:

- one story or a small cluster of tasks
- one contract change + its consumers
- one refactor (no feature mixing)

**Avoid:** branches that touch every service “a little bit”. That’s where AI-assisted work becomes unreviewable.

### 6.3 Branch protection + PR-only workflow

**Direct pushes to `main` are forbidden** once branch protection is enabled on GitHub.

All changes must:

1. Be made on a feature branch (see §6.1 naming).
2. Open a pull request against `main`.
3. Pass required CI status checks before merge:
   - `repo-guards`
   - `markdownlint`
   - `gitleaks`
4. Keep the PR branch up to date with `main` when required by branch protection.

Solo maintainer mode uses **zero required approvals** (the PR author cannot approve their own PR on GitHub). Use the PR description and checklist for self-review until team reviewers exist.

Policy details: [CONTRIBUTING.md](../CONTRIBUTING.md), [ADR-0003](/docs/adr/0003-branch-protection-and-merge-policy) on the docs site.

### 6.4 Post-merge checklist (milestones)

After a milestone PR is approved on GitHub:

1. **Squash merge and delete the remote branch** (required — avoids stale `feature/m*` branches):

   ```bash
   gh pr merge <PR_NUMBER> --squash --delete-branch
   ```

2. **Update local `main`:**

   ```bash
   git checkout main && git pull origin main
   git fetch origin --prune
   ```

3. **Optional local cleanup:** `git branch -d feature/m1-x-x-slug` if the branch still exists locally.

4. **CURRENT_STATE:** Open a small docs PR (e.g. `docs/current-state-m1-x-x`) updating [`docs/app/content/roadmap/current-state.mdx`](../app/content/roadmap/current-state.mdx) with the merge SHA — do not fold unrelated product code into that PR.

5. **Workspace archive:** Add a session note under `ibex-harness-workspace/archive/` when the milestone closes.

---

## 7) Pull Requests (PRs)

### 7.1 PR size limits

To keep reviews effective (especially with AI-generated code):

- Prefer ≤ 400 lines changed (excluding generated code, lockfiles)
- Prefer ≤ 10 files changed
- If larger: split into multiple PRs with explicit merge order

### 7.2 PR template (required)

Every PR description must include:

```markdown
## What and Why
[What changed and why it matters]

## How
[Approach taken, key design decisions]

## Testing
- [ ] Unit tests
- [ ] Integration tests
- [ ] Manual verification (describe)

## Performance
[Impact on critical path / benchmarks if relevant]

## Security
[Auth, tenant isolation, input validation considerations]

## Migrations / Ops
[DB migration, config updates, rollout notes]

## Docs
[What docs were updated; links]
```

### 7.3 Review requirements

- 1 approval: docs-only, small chores
- 2 approvals: features/fixes/refactors
- Security review required: auth, permissions, crypto, tenant isolation, token handling

### 7.4 “Definition of Done” (DoD)

A PR is mergeable only if:

- [ ] Lint passes
- [ ] Typecheck passes
- [ ] Unit tests pass
- [ ] Integration tests pass (if DB/cache touched)
- [ ] Docs updated if behavior/contracts changed
- [ ] No secrets in code/logs/tests
- [ ] Multi-tenancy constraints explicitly satisfied

---

## 8) CI/CD Expectations

### 8.1 CI gates (typical)

On PR:

- Go: `golangci-lint`, `go test ./...`
- Python: `ruff`, `mypy`, `pytest`
- TypeScript: `eslint`, `tsc`, `vitest`
- Security: secret scan, dependency scan, container scan
- Contract checks: protobuf compilation + generated code consistency

### 8.2 No “lower the bar” fixes

If a PR fails CI:

- Fix the code
- Do not disable the rule unless there is a documented, reviewed reason
- If disabling is needed, add an ADR and update `CODING_STANDARDS.md`

### 8.3 Optional pre-commit hooks

Local pre-commit hooks mirror the fast CI checks where practical. They are recommended for contributors and AI-assisted workflows.

Install:

```bash
python -m pip install pre-commit
pre-commit install
```

Run manually:

```bash
pre-commit run --all-files
```

Emergency skip:

```bash
git commit --no-verify
```

Only skip hooks for urgent or tooling-related cases. The PR description must explain what was skipped and how the equivalent CI checks were verified.

---

## 9) Contract & Schema Change Process

### 9.1 Protobuf changes

When updating `.proto`:

- Add fields only (never reuse field numbers)
- Keep old fields for compatibility (deprecate before removal)
- Regenerate clients for Go/Python/TypeScript
- Update docs + add contract tests

### 9.2 Database migrations (expand/contract)

All DB changes follow:

1. Expand: add new schema elements (safe)
2. Dual-write / backfill if needed
3. Contract: remove old elements in a later migration

**Rule:** migrations must be safe under live traffic.

---

## 10) Documentation Rules (living docs)

Documentation is part of the system. AI-assisted development depends on it.

### 10.1 Docs that must stay current

- `docs/ARCHITECTURE.md`
- `docs/API_DOCUMENTATION.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/SECURITY.md`
- `docs/TESTING_STRATEGY.md`
- `docs/CODING_STANDARDS.md`

### 10.2 ADRs (Architecture Decision Records)

Any decision that changes:

- service boundaries
- data model and lifecycle
- authz model
- scaling strategy
- migration path
- major dependency

…requires an ADR in [`docs/app/content/docs/adr/`](../app/content/docs/adr/) (public `/docs/adr`).

**ADR format (required):**

```markdown
# ADR-XXXX: Title

## Status
Proposed | Accepted | Deprecated

## Context
[Why this decision is needed]

## Options Considered
1. Option A — pros/cons
2. Option B — pros/cons

## Decision
[What we chose]

## Consequences
[Tradeoffs we accept]

## Rollout / Migration Plan
[How we implement safely]

## References
[Links]
```

---

## 11) AI-Assisted Development Workflow (Core of this Project)

### 11.1 Tool roles (what each is best for)

- Cursor/Copilot: fast local edits, pattern completion, test scaffolding
- Claude: architectural reasoning, algorithm design, cross-service consistency
- CLI models (Gemini, etc.): quick checks, diff summaries, doc drafts

### 11.2 Agent session structure (prevents drift)

A productive session has 5 phases:

1. **Orientation (5–10 min)**
   - confirm target issue + constraints
   - inspect existing code patterns
   - list assumptions + how to verify them

2. **Design checkpoint (5–10 min)**
   - sketch the minimal structure
   - define interfaces and error shapes
   - confirm where files go (framework conventions)

3. **Implementation**
   - happy path first
   - then failure paths
   - then instrumentation (metrics/logs)

4. **Verification**
   - run lint/typecheck/tests locally
   - add missing tests
   - check tenant isolation and authz

5. **Handoff**
   - update notes + decisions
   - record what’s done / what remains

### 11.3 Hallucination control (practical rules)

AI assistants hallucinate most often when:

- asked to implement across too many files at once
- missing actual repository references
- asked to “fill in the rest” without constraints

**Required behavior:**

- If you can’t point to the file or type in the repo, do not invent it.
- Prefer: “I cannot find X in the repo. Should we create it as Y?”

### 11.4 Issue decomposition (AI-friendly)

A good AI-executable task:

- touches ≤ 5–8 files
- introduces ≤ 1 new abstraction
- has explicit acceptance criteria
- includes failure cases and tests

Avoid tasks like:

- “Implement the entire memory system”
- “Set up all infra”

These become drift factories.

---

## 12) Session Workspace (required layout, outside repo)

AI sessions lose context. Keep a **session workspace** next to the git clone (never committed). The versioned roadmap in `docs/app/content/roadmap/` describes *what to build*; the workspace holds *session continuity*, *archived audits*, and *execution prompts*.

### 12.0 Recommended host layout

Use a parent directory with **two siblings**:

```text
<parent>/
  ibex-harness/                 # git clone (this repository)
  ibex-harness-workspace/       # local only — see below
```

Examples:

- Windows: `D:\ibex-r\ibex-harness` and `D:\ibex-r\ibex-harness-workspace`
- macOS/Linux: `~/ibex-r/ibex-harness` and `~/ibex-r/ibex-harness-workspace`

After cloning, create the workspace folder manually or copy the structure from this section. **Do not** store session files under `reports/` inside the repo (removed).

### 12.1 Discovery

**Default:** If the repository root is `<parent>/ibex-harness`, the workspace is `<parent>/ibex-harness-workspace`.

**Override:** Set `IBEX_WORKSPACE_DIR` to the workspace root (absolute path). Tools and agents should read [DEVELOPMENT_GUIDE.md](DEVELOPMENT_GUIDE.md) §12 rather than hardcoding host paths.

### 12.2 Workspace tree

```text
ibex-harness-workspace/
  current_state.md          # session scratch; pointers to docs/app/content/roadmap/current-state.mdx
  decisions.md
  active_task.md
  handoff.md
  known_issues.md
  contracts.md
  prompts/                  # milestone execution prompts (not published on docs site)
  pr-bodies/                # PR description drafts (full template); never commit to git repo
    pr-<number>-<slug>.md
  session_log/
    2026-05-30-session-01.md
  archive/
    foundation/               # closed implementation audits (formerly repo-local reports/)
      INDEX.md
      001-....md
```

### 12.3 Sync with the roadmap

After each milestone merges to `main`:

1. Update [`docs/app/content/roadmap/current-state.mdx`](../app/content/roadmap/current-state.mdx) in the repo (via PR).
2. Refresh workspace `current_state.md` and `handoff.md`.
3. Log surprises in [`docs/app/content/roadmap/findings.mdx`](../app/content/roadmap/findings.mdx) when the plan changes.
4. Do **not** rewrite files under `archive/`; add new session log entries instead.

### 12.4 Minimal templates

**current_state.md**

```markdown
# Session current state

Canonical status: `docs/app/content/roadmap/current-state.mdx` in the repo (public `/roadmap/current-state`).

| Field | Value |
| --- | --- |
| main SHA | ... |
| Next milestone | ... |

## This session
- ...
```

**handoff.md**

```markdown
# Handoff

## What was attempted
...

## What was completed
- ...

## What remains
- ...

## Decisions made
- ...

## Risks / gotchas
- ...

## How to verify
- commands to run
- expected outputs
```

**contracts.md**

```markdown
# Contract Registry

## Protobuf
- packages/proto/...

## REST
- docs/API_DOCUMENTATION.md sections updated

## DB
- docs/DATABASE_SCHEMA.md updated
- migration file: services/.../alembic/versions/...
```

---

## 13) Refactoring Policy (planned, not accidental)

Refactoring is expected. AI-generated code tends to accumulate:

- duplicated patterns
- overly long functions
- inconsistent naming
- weak error boundaries

### 13.1 When refactoring is required

Refactor before adding features if:

- cyclomatic complexity > limits
- repeated logic appears in 3+ places
- a module is both high-churn and high-complexity
- cross-service duplication exists in critical logic (authz, tenant scoping)

### 13.2 Refactor constraints

- Refactor PRs do not change behavior (unless explicitly stated)
- Require tests first (or in same PR)
- Prefer small refactors over “rewrite everything”

---

## 14) Release Discipline (lightweight)

### 14.1 Versioning

- Services: semantic versioning
- Public REST API: major version in URL (`/v1`)
- Protobuf: additive evolution only; breaking changes require new message/service

### 14.2 Release checklist (minimum)

- [ ] All CI green
- [ ] Migrations reviewed and safe
- [ ] Rollback plan documented
- [ ] Metrics/alerts updated for new features
- [ ] Sentry release created (if enabled)

---

## 15) Getting Started Checklist (first day)

1. Clone under a parent directory (e.g. `ibex-r/ibex-harness`) and create sibling `ibex-harness-workspace/` per §12
2. Start local infra via Compose
3. Run migrations + seed
4. Run one service at a time (auth → proxy → memory)
5. Call health endpoints
6. Run test suite
7. Create first small issue (e.g., `/health` endpoints)
8. Enforce CI early (do not defer quality gates)

---

## Appendix A: Commands (recommended Make targets)

These are recommended and should be implemented as the repo matures:

```bash
make dev                 # start core services and deps
make lint                # run all linters
make typecheck           # mypy + tsc + go build checks
make test                # unit tests
make compose-test-up     # Postgres on port 5433 for integration tests (default local mode)
make test-integration    # all Go integration tests (-tags=integration)
make db-migrate          # apply migrations
make db-seed             # seed dev org/user/agent
make proto-gen           # regenerate protobuf clients
make format              # gofmt + ruff format + prettier
```

**Integration tests (Go):**

- Default: `make compose-test-up` then `make test-integration` (uses `POSTGRES_TEST_DSN` or port 5433).
- Self-contained testcontainers: deferred (see `DEPENDENCIES.md` §8.2.1); use compose test stack for now.
- CI uses GitHub Actions service Postgres in `auth-validate-smoke` / `db-migrate-smoke` (no testcontainers in merge gates).

**Windows (PowerShell):**

- Set env vars with `$env:NAME = "value"` then run the command on the next line — do **not** paste bash `VAR=value cmd` or `\` line continuations.
- Integration tests with `compose-dev-up` only: `$env:POSTGRES_TEST_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"` before `go test -tags=integration ./...`
- Service runbooks: [services/auth/README.md](../services/auth/README.md), [services/proxy/README.md](../services/proxy/README.md)

---

This development guide defines how we keep IBEX Harness consistent and high quality as we build it with AI assistance.
