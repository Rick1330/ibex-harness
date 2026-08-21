# IBEX Harness — File Structure (Monorepo Layout)

## 1) Purpose

This document defines the **canonical repository structure** for IBEX Harness:

- where each service lives,
- how each service is structured internally,
- where shared packages and generated code live,
- how to keep frameworks (Go/FastAPI/Next.js) consistent,
- and what changes require an ADR.

This exists because AI-assisted development fails badly when:

- file locations are underspecified,
- framework conventions are not enforced,
- “utility” modules accumulate randomly,
- generated code is committed inconsistently,
- service boundaries become blurry over time.

**Rule:** If you add a new top-level directory or a new deployable service, justify it (usually via ADR) and update [`services/README.md`](../../services/README.md) / [`packages/README.md`](../../packages/README.md).  
**Rule:** If you add a new file pattern inside a service, follow the service scaffold conventions below — treat scaffolds as orientation, not a rigid file checklist.  
**Rule:** Engineering docs and the public roadmap must stay aligned when phase scope or service inventory changes.

---

## 2) Top-Level Layout (Canonical)

Living engineering docs live under `web/engineering/` (this tree). Integrator-facing docs and the
public roadmap live under `web/content/`. Do **not** add a parallel top-level `docs/` tree.

```text
ibex-harness/
  AGENTS.md
  CLAUDE.md
  README.md
  LICENSE
  Makefile
  go.mod                       # single Go module for services + packages
  go.sum
  .golangci.yml
  .pre-commit-config.yaml

  services/                    # deployable processes — see services/README.md
    proxy/                     # Go — LLM proxy (shipped; grows in 2.5+)
    auth/                      # Go — auth (shipped; grows in 4)
    embedder/                  # Python — embeddings (planned 2.5)
    tokenizer-service/         # Python — token counts (planned 2.5, situational)
    mcp-memory/                # Python — MCP memory tools (2.5 skeleton → 3.5)
    memory/                    # Python — memory substrate (planned 3)
    worker/                    # Python Celery — extraction / jobs (planned 3.5+)
    context/                   # Python gRPC — context assembly (planned 3.5)
    api/                       # Python FastAPI — management plane (planned 4)
    dashboard/                 # Next.js — operator UI (planned 4)

  packages/                    # shared libraries — see packages/README.md
    proto/                     # protobuf source of truth + codegen
    provider/                  # LLM provider abstraction (extends in 2.5+)
    # planned: tokenizer/, responsepipeline/, embedder/, contextclient/, circuitbreaker/
    # planned SDKs/CLI: sdk-python/, sdk-typescript/, sdk-go/, cli/

  infra/
    compose/dev/               # local dependencies (available)
    compose/test/              # CI/integration compose (available)
    migrations/                # Postgres + ClickHouse migrations (available)
    scripts/                   # operational helpers (available)
    docker/ helm/ terraform/ monitoring/   # planned; not all present yet

  benchmarks/                  # proxy overhead + load pipeline (available); retrieval eval grows later
  web/
    content/docs/              # public /docs
    content/roadmap/           # public /roadmap (phases 0–5 redesigned)
    engineering/               # this living engineering doc set
    src/                       # Next.js public site

  tools/                       # optional small dev tooling
```

### 2.1 What belongs where?

- **services/**: deployable runtime components (anything that runs as a process)
- **packages/**: shared libraries and contracts (proto, provider, future SDKs/CLI)
- **infra/**: deployment, orchestration, observability, local dev infrastructure, migrations
- **web/engineering/**: living engineering documentation (this directory)
- **web/content/**: public site MDX (docs, roadmap, blog)
- **benchmarks/**: proxy/load benchmark pipeline; later phases add retrieval/eval harnesses under services or here with an ADR

### 2.2 What does NOT belong at top-level?

Avoid adding:

- `utils/` (too vague; becomes junk drawer)
- `scripts/` at top-level (use `infra/scripts/` unless truly universal)
- random `config/` directories (service-specific config should live with the service)
- a second `docs/` tree alongside `web/engineering/`

### 2.3 Inventory is a planning baseline

Service and package directories named above are the **current planning baseline** from the redesigned
roadmap. Exact names, merges, and splits may change during implementation when there is strong
evidence — record an ADR and update [`services/README.md`](../../services/README.md) /
[`packages/README.md`](../../packages/README.md).

---

## 3) Service Scaffold Conventions

Every service must include (minimum):

- `README.md` (service-specific)
- `.env.example`
- `Dockerfile`
- `Makefile` targets (or root Makefile targets that can run it)
- `/health` and `/ready` endpoints
- structured logging setup
- metrics endpoint (where relevant)

### 3.1 Go services (proxy, auth, cli)

Canonical layout:

```text
services/proxy/
  cmd/
    proxy/
      main.go                  # entrypoint only
  internal/
    config/                    # env config parsing + validation
    http/                      # HTTP server wiring (router/middleware)
    llm/                       # OpenAI chat request parse + context (M1.2.2+)
    validation/                # semantic limits + header validation (M1.2.3)
    auth/                      # token validation (consumer-side interfaces)
    ratelimit/                 # token bucket + lua scripts
    upstream/                  # provider adapter layer
    context/                   # context assembly client
    streaming/                 # stream muxing/backpressure
    circuit/                   # circuit breakers
    metrics/                   # Prometheus metrics definitions
    observability/             # OTel setup, trace helpers
    errors/                    # shared error mapping (service-local)
  pkg/                         # only if intentionally shared outside service
  test/
    integration/               # optional if not co-located
  .env.example
  Dockerfile                   # build from repo root; see service README
  README.md
```

`services/auth/` follows the same `cmd/` + `internal/` layout. Notable paths after M1.1.7:

- `internal/repository/tokens.go` — PAT persistence and lookup (service-account RLS)
- `internal/repository/agents.go` — `GetByIDAndOrg` for `ValidateAgent` gRPC (M1.1.7)
- `internal/grpc/server.go` — `ValidateToken`, `ValidateAgent`, token management RPCs

Note: this repository uses a single root Go module (`go.mod` at repository root) for monorepo convenience. Service directories should *not* contain independent module files unless there is a deliberate reason to opt-in to per-service versioning; prefer the root module so tooling (`go test ./...`, `gofmt`, `golangci-lint`) runs from repository root.

**Rules:**

- Go services use the **repository root** `go.mod` (`github.com/Rick1330/ibex-harness`). Do not add per-service `go.mod` files.
- `cmd/<service>/main.go` contains **wiring only** (config + start + graceful shutdown).
- `internal/` contains almost all logic.
- `pkg/` is only for code intended to be imported by other modules. Default is **do not use pkg**.
- Tests should generally be co-located with source (`*_test.go`) unless integration suites need a separate directory.

### 3.2 Python services (FastAPI + async SQLAlchemy)

Canonical layout:

```text
services/memory/
  src/
    ibex_memory/
      __init__.py
      main.py                  # FastAPI app creation + router registration
      config.py                # pydantic-settings config + validation
      dependencies.py          # auth claims + db + redis dependencies
      routers/                 # API boundary (request/response orchestration)
        __init__.py
        health.py
        memories.py
        search.py
      services/                # business logic and algorithms
        __init__.py
        memory_service.py
        dedup_service.py
        conflict_service.py
      repositories/            # DB/Redis access only (no policy decisions)
        __init__.py
        memory_repository.py
        cache_repository.py
      models/                  # domain models + Pydantic request/response models
        __init__.py
        domain.py              # dataclasses (internal)
        requests.py            # pydantic request models
        responses.py           # pydantic response models
      core/                    # shared wiring: db, redis, logging, errors
        __init__.py
        database.py
        redis.py
        logging.py
        errors.py
        security.py
      telemetry/               # OTel wiring/helpers (if needed)
        __init__.py
        tracing.py
  alembic/
    alembic.ini
    env.py
    versions/
  tests/
    unit/
    integration/
    conftest.py
  pyproject.toml
  uv.lock
  .env.example
  Dockerfile
  README.md
```

**Rules:**

- Every router file must be thin (validation + DI + calling service layer).
- Every DB query lives in `repositories/`.
- All “what should happen” logic belongs in `services/`.
- Models:
  - Pydantic models for API request/response (boundary types)
  - Dataclasses or simple domain types internally (optional)
- Integration tests must use real DB/Redis (testcontainers).

### 3.3 Python worker service (Celery)

Preferred starting worker stack for Phase **3.5+** (extraction, embedding jobs, maintenance; later fingerprint/drift/regression in **4.5**). Alternatives (e.g. Temporal) only with evidence + ADR.

Canonical layout (illustrative — exact module names may differ):

```text
services/worker/
  src/
    ibex_worker/
      __init__.py
      config.py
      celery_app.py            # Celery app + routing + retry policies
      tasks/
        __init__.py
        memory_extraction.py   # Phase 3.5
        embedding_jobs.py
        maintenance.py
        fingerprinting.py      # Phase 4.5
        drift_detection.py     # Phase 4.5
        regression.py          # Phase 4.5
      clients/                 # HTTP/gRPC clients to other services
        __init__.py
        memory_client.py
        embedder_client.py
        clickhouse_client.py
      core/
        __init__.py
        logging.py
        telemetry.py
        idempotency.py
        errors.py
  tests/
    unit/
    integration/
  pyproject.toml
  uv.lock
  .env.example
  Dockerfile
  README.md
```

**Rules:**

- Tasks must be idempotent (explicit idempotency keys).
- Retries must be explicit and categorized (transient vs permanent).
- Tasks must never log sensitive content.
- Queue topology is situational — confirm against live Redis/Celery constraints during implementation.

### 3.4 Next.js dashboard (App Router) — TypeScript

Canonical layout (Next.js 14+ App Router):

```text
services/dashboard/
  src/
    app/
      (auth)/
        login/
          page.tsx
        layout.tsx
      (dashboard)/
        agents/
          page.tsx
          [agentId]/
            page.tsx
            sessions/
              page.tsx
        memories/
          page.tsx
        directives/
          page.tsx
        layout.tsx
      api/
        auth/
          route.ts             # server route handlers if needed
      layout.tsx
      error.tsx                # root error boundary
      not-found.tsx
      loading.tsx
      globals.css

    components/
      ui/                      # base components: Button, Input, Modal
      agent/
      session/
      memory/
      directive/
      charts/

    hooks/                     # React Query hooks, small + focused
    lib/
      api/                     # typed API client
      auth/                    # server-only auth helpers
      telemetry/
      utils/
    stores/                    # Zustand stores (UI state only)
    types/                     # stable TS types (generated + handwritten)
  public/
  tests/
    unit/
    e2e/                       # Playwright tests
  next.config.js
  tsconfig.json
  tailwind.config.ts
  package.json
  .env.example
  README.md
```

**Server vs Client component rules:**

- Default to server components (`page.tsx` is usually server)
- Use `"use client"` only in leaf interactive components
- Never import server-only modules into client components
- Every data-heavy view must have:
  - loading state
  - error state
  - empty state

---

## 4) Packages Scaffold Conventions

### 4.1 `packages/proto` (source of truth)

Canonical layout:

```text
packages/proto/
  buf.yaml
  buf.gen.yaml
  buf.work.yaml                 # optional, if multi-module
  proto/
    ibex/
      context/v1/context.proto
      memory/v1/memory.proto
      auth/v1/auth.proto
      session/v1/session.proto
      directive/v1/directive.proto
      common/v1/common.proto
  gen/
    go/                         # generated Go code (committed or generated in CI; decide via ADR)
    python/
    typescript/
  README.md
```

**Rules:**

- `.proto` files live in `packages/proto/proto/...`
- Generated output goes in `packages/proto/gen/<lang>/...`
- Use `buf` for linting, breaking-change detection, code generation.
- Field numbers are never reused. Breaking changes require versioned messages/services.

**Decision required early (ADR):**

- Do we commit generated code to git or generate in CI?
  - Committing reduces toolchain friction for consumers.
  - Not committing reduces diffs/noise and avoids stale generation.
  - Either is acceptable, but it must be consistent and enforced.

### 4.2 SDKs

Canonical layout:

```text
packages/sdk-python/
  src/ibex_sdk/
    __init__.py
    client.py
    memory.py
    sessions.py
    directives.py
    errors.py
    types.py                 # generated types or wrappers
  tests/
  pyproject.toml
  README.md

packages/sdk-typescript/
  src/
    index.ts
    client.ts
    memory.ts
    sessions.ts
    directives.ts
    errors.ts
    types.ts
  test/
  package.json
  tsconfig.json
  README.md

packages/sdk-go/
  client/
  memory/
  sessions/
  directives/
  errors/
  go.mod
  README.md
```

**Rules:**

- SDKs are thin wrappers. No heavy dependencies.
- SDKs must not embed service internals.
- SDKs must expose stable error types and retry behavior.

### 4.3 CLI

Canonical layout:

```text
packages/cli/
  cmd/ibex/
    main.go
  internal/
    commands/
      root.go
      auth.go
      memory.go
      session.go
      directive.go
      trace.go
    config/
    output/
  go.mod
  README.md
```

---

## 5) Infrastructure Layout

### 5.1 Docker Compose

Canonical layout:

```text
infra/compose/
  dev/
    docker-compose.yml
    .env.example
  test/
    docker-compose.yml
  README.md
```

**Rules:**

- `dev` compose emphasizes convenience
- `test` compose emphasizes reproducibility and isolation
- Compose files must expose ports consistently:
  - Postgres: 5432
  - Redis: 6379
  - ClickHouse HTTP: 8123
  - MinIO: 9000 (API), 9001 (console)

### 5.2 Helm Charts

Canonical layout:

```text
infra/helm/
  ibex-harness/
    Chart.yaml
    values.yaml
    values-staging.yaml
    values-prod.yaml
    templates/
      proxy/
      auth/
      api/
      memory/
      context/
      embedder/
      worker/
      dashboard/
      postgresql/            # optional if self-hosted DB
      redis/                 # optional if self-hosted Redis
      clickhouse/            # optional if self-hosted
      minio/                 # optional if self-hosted
    README.md
```

**Rules:**

- Each service gets its own Deployment/Service/HPA templates.
- Values are hierarchical and consistent across services.
- No secrets in git; use external secrets mechanisms.

### 5.3 Terraform

Canonical layout:

```text
infra/terraform/
  modules/
    network/
    k8s/
    databases/
    redis/
    clickhouse/
    storage/
    monitoring/
  envs/
    dev/
    staging/
    prod/
  README.md
```

---

## 6) Generated Code Policy (Critical for AI Reliability)

Generated code is a frequent source of drift:

- stale generated outputs
- mismatched versions
- accidental manual edits

**Rules:**

1. Generated code directories must include a warning header:
   - “DO NOT EDIT — generated by buf”
2. CI must verify generation consistency:
   - run `make proto-gen`
   - fail if git diff shows uncommitted changes
3. Developers must never modify generated code by hand.

---

## 7) “Allowed to Create” vs “Forbidden to Create”

### Allowed (when justified)

- New service under `services/` with full scaffold — update [`services/README.md`](../../services/README.md) + ADR when inventing a new process boundary
- New shared library under `packages/` — update [`packages/README.md`](../../packages/README.md) + ADR when promoting shared contracts
- New proto package version under `packages/proto/proto/ibex/...`
- New engineering docs under `web/engineering/` and public ADRs under `web/content/docs/adr/`
- New roadmap MDX under `web/content/roadmap/`
- New infra module under `infra/` — update [`infra/README.md`](../../infra/README.md)

### Forbidden patterns

- `utils/` catch-all packages
- random top-level `scripts/` not under `infra/scripts`
- adding `lib/` folders inside Go services as dumping grounds
- mixing business logic into API routers/handlers
- putting DB queries into service layer (Python)
- putting server-only code into Next.js client components
- recreating a top-level `docs/` tree parallel to `web/engineering/`

---

## 8) ADR Triggers (When You Must Write an ADR)

Write an ADR if you change:

- service boundaries or responsibilities
- contract strategy (proto organization/versioning)
- persistence strategy (pgvector → Qdrant migration plan)
- auth model (permissions, token types, rotation policy)
- tenant isolation enforcement mechanisms
- infrastructure orchestration approach
- generated code policy (commit vs generate)
- major dependencies

---

## 9) “AI Agent Guardrails” for File Placement

AI agents often put files in wrong places because:

- they follow their training defaults (common patterns from other projects),
- they try to simplify structure,
- they lose track of a path mentioned earlier.

**To prevent this:**

- Always provide the target tree in the issue/task prompt.
- Always state “do not create additional directories” unless required.
- Always state “follow the nearest existing sibling pattern.”

**Example instruction block to paste into tasks:**

```text
File placement rules:
- Prefer placing files only under these directories:
  - services/<service-name>/...
  - packages/<package-name>/...
  - infra/...
  - web/engineering/...
  - web/content/docs/... or web/content/roadmap/...
- Do NOT create new top-level directories without an ADR.
- Match the existing layout in services/<service-name>.
- Treat scaffolds as orientation — exact filenames may differ when live patterns say so.
- If a file path conflicts with framework conventions, stop and ask.
```

---

## 10) Verification Checklist (Structure “Done”)

Before merging a PR that creates or moves files:

- [ ] Tree matches this document (or an ADR explains the deliberate divergence)
- [ ] Service scaffold includes README + `.env.example` + Dockerfile when introducing a new deployable
- [ ] No new junk-drawer directories (`utils`, `helpers`, etc.)
- [ ] Generated code not edited manually
- [ ] Imports reflect boundaries (no cross-layer coupling)
- [ ] Inventories updated (`services/README.md` / `packages/README.md` / `infra/README.md` as needed)
- [ ] Roadmap / engineering docs updated when phase scope or public contracts change
- [ ] CI generation checks pass

---

This file structure is part of the architecture.
If structure drifts, quality and AI reliability degrade rapidly.
Keep it strict.
