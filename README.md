# IBEX Harness

Production-grade platform for AI agent memory, context assembly, and secure LLM proxying.

**Phase 1 (current):** `auth` and `proxy` services are implemented. See [docs/roadmap/CURRENT_STATE.md](docs/roadmap/CURRENT_STATE.md) for what ships today and what is next.

[![CI](https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/Rick1330/ibex-harness/graph/badge.svg)](https://codecov.io/gh/Rick1330/ibex-harness)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CodeScene Average Code Health](https://codescene.io/projects/80943/status-badges/average-code-health)](https://codescene.io/projects/80943)
[![CodeScene System Mastery](https://codescene.io/projects/80943/status-badges/system-mastery)](https://codescene.io/projects/80943)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/Rick1330/ibex-harness)

## Getting started

**Prerequisites:** Docker, Go 1.25.11+, Buf CLI, GNU Make — full list in [docs/TOOLCHAIN.md](docs/TOOLCHAIN.md).

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness

make compose-dev-up
make db-migrate
make db-seed

cp services/auth/.env.example services/auth/.env
cp services/proxy/.env.example services/proxy/.env
```

Start services (two terminals):

```bash
# Terminal 1 — auth (HTTP :8081, gRPC :9091)
go run ./services/auth/cmd/auth

# Terminal 2 — proxy (:8080); 2s auth timeout needed for local Argon2 verify
IBEX_AUTH_VALIDATE_TIMEOUT=2s go run ./services/proxy/cmd/proxy
```

**Windows (PowerShell):**

```powershell
# Terminal 1 — auth
$env:POSTGRES_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
$env:IBEX_PORT = "8081"
$env:IBEX_GRPC_PORT = "9091"
go run ./services/auth/cmd/auth

# Terminal 2 — proxy
$env:REDIS_URL = "redis://localhost:6379/0"
$env:IBEX_AUTH_GRPC_ADDR = "127.0.0.1:9091"
$env:IBEX_AUTH_VALIDATE_TIMEOUT = "2s"
$env:IBEX_PORT = "8080"
go run ./services/proxy/cmd/proxy
```

Verify the pipeline:

```bash
make dev-smoke
```

Full workflow: [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md). Environment registry: [docs/ENVIRONMENT_VARIABLES.md](docs/ENVIRONMENT_VARIABLES.md).

```bash
make compose-dev-down   # stop infrastructure when done
```

## Repository

| Path | Status |
|------|--------|
| `services/auth` | Implemented — token validation, permissions, health endpoints |
| `services/proxy` | Implemented — auth gate, rate limits, `/v1/*` stub |
| `packages/config`, `packages/apierror` | Implemented — shared env load and error envelope |
| `packages/proto` | Implemented — protobuf contracts (Buf) |
| `infra/compose`, `infra/migrations` | Implemented — local dev and schema |
| `services/api`, `memory`, `context`, `dashboard`, SDKs, CLI | Planned — see [roadmap](docs/roadmap/CURRENT_STATE.md) |

Target architecture and data flows: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md).

## Documentation

**Index:** [docs/README.md](docs/README.md)

| Area | Document |
|------|----------|
| Status & roadmap | [docs/roadmap/CURRENT_STATE.md](docs/roadmap/CURRENT_STATE.md) |
| Architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Security | [docs/SECURITY.md](docs/SECURITY.md) |
| Development | [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) |
| Testing | [docs/TESTING_STRATEGY.md](docs/TESTING_STRATEGY.md) |
| AI workflow | [AGENTS.md](AGENTS.md) |

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request. By participating, you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).

**Security:** report vulnerabilities via [.github/SECURITY.md](.github/SECURITY.md) — do not open public issues for security findings.

**Support:** see [.github/SUPPORT.md](.github/SUPPORT.md).

## License

[MIT](LICENSE)
