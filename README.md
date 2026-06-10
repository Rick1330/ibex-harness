# IBEX Harness

[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Rick1330/ibex-harness)

IBEX Harness is a production-grade AI agent memory and context management platform. It provides:

- Persistent memory (write, deduplicate, retrieve, conflict-resolve)
- Intelligent context assembly (budgeting, ranking, injection)
- Behavioral fingerprinting + drift detection
- Session lifecycle management (heartbeat, checkpoint, resume)
- Directive versioning (safe prompt changes, regression checks)
- Developer tools: SDKs, CLI, dashboard, integrations

This repository is a monorepo containing all services, packages, and infrastructure needed to run IBEX Harness locally and in production.

---

## Quick Start (Local Development)

### Prerequisites

- Docker + Docker Compose
- Go 1.22+
- Python 3.11+
- Node.js 18+
- Buf CLI
- GNU Make (run `make` from Git Bash on Windows; Git Bash alone does not include Make)

Install and verify tools with [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md).

**Development roadmap:** [docs/roadmap/CURRENT_STATE.md](docs/roadmap/CURRENT_STATE.md) (what works, what is next).

### 1) Clone

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness
```

### 2) Start infrastructure (databases, caches, analytics)

```bash
make compose-dev-up
```

Expected services:

- PostgreSQL (with pgvector)
- Redis (Redis Stack recommended)
- ClickHouse
- MinIO (S3-compatible)

### 3) Run migrations and seed development data

```bash
make db-migrate
make db-seed
```

`make db-seed` is idempotent and creates a fixed dev org, user, agent, and PAT. See [DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) for the seed PAT wire format (ADR-0007).

### 4) Configure service environment files

```bash
cp services/auth/.env.example services/auth/.env
cp services/proxy/.env.example services/proxy/.env
```

Edit both files as needed. Defaults in `.env.example` match the local Compose stack (`postgres://ibex:ibex@localhost:5432/ibex`, `redis://localhost:6379/0`).

### 5) Start Go services and run smoke test

From the repository root (two terminals or background):

```bash
# Terminal 1 — auth (HTTP :8081, gRPC :9091)
go run ./services/auth/cmd/auth

# Terminal 2 — proxy (:8080)
# Local dev: use a higher auth gRPC timeout (50ms default is too low for Argon2 verify on many laptops)
IBEX_AUTH_VALIDATE_TIMEOUT=2s go run ./services/proxy/cmd/proxy
```

**Windows (PowerShell):**

```powershell
# Terminal 1 — auth
$env:POSTGRES_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
$env:IBEX_PORT = "8081"
$env:IBEX_GRPC_PORT = "9091"
go run ./services/auth/cmd/auth

# Terminal 2 — proxy (2s auth timeout required for local smoke on Windows)
$env:REDIS_URL = "redis://localhost:6379/0"
$env:IBEX_AUTH_GRPC_ADDR = "127.0.0.1:9091"
$env:IBEX_AUTH_VALIDATE_TIMEOUT = "2s"
$env:IBEX_PORT = "8080"
go run ./services/proxy/cmd/proxy
```

Verify the auth → proxy pipeline:

```bash
make dev-smoke
```

Export the dev PAT for manual curls:

```bash
export IBEX_DEV_TOKEN=ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY
```

Full workflow: [DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md). Environment registry: [ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

### 6) Run local validation

```bash
make repo-guards
make lint-docs
make proto-lint
```

### 7) Stop infrastructure

```bash
make compose-dev-down
```

Application services are introduced incrementally. Do not assume product endpoints exist until the relevant service README documents them.

---

## Repository Layout

```text
ibex-harness/
  services/
    proxy/            # Go: latency-critical LLM proxy
    auth/             # Go: auth service (token validation, permissions)
    api/              # Python: REST management plane
    memory/           # Python: memory CRUD + vector search
    context/          # Python: context assembly engine (gRPC)
    embedder/         # Python: embedding generation service
    worker/           # Python: async workers (Celery)
    dashboard/        # Next.js: web dashboard

  packages/
    proto/            # protobuf definitions (source of truth)
    sdk-python/
    sdk-typescript/
    sdk-go/
    cli/              # Go: ibex CLI

  infra/
    compose/
      dev/
      test/
    docker/
    k8s/
    helm/
    terraform/
    monitoring/

  docs/                 # all technical documentation (see docs/README.md)
  prompts/              # AI prompt library (.txt files)
  AGENTS.md             # global AI agent operating manual
  PROMPTS.md            # prompt library index
  .cursorrules          # Cursor IDE rules
```

---

## Documentation

**Index:** [docs/README.md](docs/README.md)

| Area | Document |
|------|----------|
| Vision | [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Database schema | [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md) |
| APIs | [docs/API_DOCUMENTATION.md](docs/API_DOCUMENTATION.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Development | [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) |
| Testing | [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) |
| Env vars | [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md) |
| Runbooks | [docs/runbooks/RUNBOOKS.md](docs/runbooks/RUNBOOKS.md) |
| AI workflow | [AGENTS.md](AGENTS.md) · [prompts/](prompts/) |

---

## Core System Concepts

### LLM Proxy

The Go proxy sits between agent code and LLM providers. It:

- Validates tokens and permissions
- Enforces rate limits
- Assembles and injects context (directives + memories)
- Forwards requests to providers (supports streaming)
- Emits traces and triggers async memory extraction

Latency is the primary constraint: proxy overhead must remain extremely low.

### Memory

A memory is a structured piece of information stored for retrieval later:

- Has category, confidence, usefulness, and lifecycle status
- Has a vector embedding for semantic retrieval
- Is tenant-isolated by org_id (RLS + defense-in-depth)

### Context Assembly

The context engine selects which directive + history + memories to inject per request, under a token budget. It ranks memories using a composite scoring function and packs them into the available context space.

### Sessions

A session tracks agent execution with:

- Heartbeats for liveness detection
- Checkpoints for crash recovery
- Replay events for debugging and dashboards

### Directives

Directives are versioned instruction sets for agents (like Git commits). Promotions are gated by regression scenarios and can be rolled back/revoked safely.

---

## Development Workflow

### Branches

- `main`: stable, always releasable
- `feature/*`: new features
- `fix/*`: bug fixes
- `security/*`: security changes

### Pull Requests

Every PR must:

- Pass lint + typecheck + tests
- Include relevant docs updates
- Include migration steps if schema changed
- Avoid secret leakage and unsafe logging

See `docs/CODING_STANDARDS.md` for PR conventions and limits.

---

## Configuration

### Environment Variables

Each service has its own `.env` support in dev. Use:

- `.env.example` files in each service folder (to be created)
- `infra/compose/dev/docker-compose.yml` for local defaults

At minimum you will configure:

- PostgreSQL DSN
- Redis URL
- ClickHouse URL
- MinIO credentials and endpoint
- LLM provider keys (optional in dev, can run in mock mode)

---

## Security & Multi-Tenancy

IBEX Harness enforces tenant isolation with:

- PostgreSQL Row-Level Security (RLS) for every tenant table
- org_id namespacing for Redis keys
- org_id filters enforced in ClickHouse queries
- structured audit logs for sensitive operations

See `docs/SECURITY.md` for threat model and implementation rules.

---

## Observability

- Metrics: Prometheus
- Logs: Loki
- Traces: OpenTelemetry (Tempo/Jaeger)
- Errors: Sentry

---

## License

[MIT](LICENSE)

---

## Contributing

1. Read `docs/DEVELOPMENT_GUIDE.md`
2. Follow `docs/CODING_STANDARDS.md`
3. Keep PRs small and reviewable
4. Never commit secrets
