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
    adr/                    # architecture decision records
```

**Rule:** Don’t invent new top-level directories casually. If you need one, justify it with an ADR.

---

## 4) Local Development (the “one hour rule”)

A new contributor should be able to get productive in **≤ 1 hour**.

### 4.1 Prerequisites

- Docker + Docker Compose
- Go 1.21+
- Python 3.11+
- Node.js 18+

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

```bash
make db-migrate
make db-seed
```

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

Policy details: [CONTRIBUTING.md](../CONTRIBUTING.md), [adr/ADR-0003-branch-protection-and-merge-policy.md](adr/ADR-0003-branch-protection-and-merge-policy.md).

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

…requires an ADR in `docs/adr/`.

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

## 12) Session Workspace (recommended, outside repo)

Because AI sessions lose context, maintain a workspace folder (not committed):

```text
~/ibex-harness-workspace/
  current_state.md
  decisions.md
  active_task.md
  handoff.md
  known_issues.md
  contracts.md
  session_log/
    2026-05-30-session-01.md
```

### 12.1 Minimal templates

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

1. Start local infra via Compose
2. Run migrations + seed
3. Run one service at a time (auth → proxy → memory)
4. Call health endpoints
5. Run test suite
6. Create first small issue (e.g., `/health` endpoints)
7. Enforce CI early (do not defer quality gates)

---

## Appendix A: Commands (recommended Make targets)

These are recommended and should be implemented as the repo matures:

```bash
make dev                 # start core services and deps
make lint                # run all linters
make typecheck           # mypy + tsc + go build checks
make test                # unit tests
make test-integration    # integration tests via testcontainers
make db-migrate          # apply migrations
make db-seed             # seed dev org/user/agent
make proto-gen           # regenerate protobuf clients
make format              # gofmt + ruff format + prettier
```

---

This development guide defines how we keep IBEX Harness consistent and high quality as we build it with AI assistance.
