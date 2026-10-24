<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="site/public/brand/ibex-mark-dark.png">
    <img alt="IBEX Harness" src="site/public/brand/ibex-mark-light.png" width="96" height="96">
  </picture>
</p>

<h1 align="center">IBEX Harness</h1>

<p align="center">AI-agent memory, context assembly, and secure LLM proxying for multi-tenant systems.</p>

<p align="center">
  <a href="https://ibexharness.com">Docs</a> ·
  <a href="https://ibexharness.com/benchmarks">Benchmarks</a> ·
  <a href="engineering/DEVELOPMENT_GUIDE.md">Developer guide</a> ·
  <a href="engineering/SECURITY.md">Security</a>
</p>

<p align="center">
  <a href="https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://codecov.io/gh/Rick1330/ibex-harness"><img alt="codecov" src="https://codecov.io/gh/Rick1330/ibex-harness/graph/badge.svg"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/Rick1330/ibex-harness&platform=github.com"><img alt="OpenSSF Scorecard" src="https://api.securityscorecards.dev/projects/github.com/Rick1330/ibex-harness/badge"></a>
  <a href="https://www.bestpractices.dev/projects/13590"><img alt="OpenSSF Best Practices" src="https://www.bestpractices.dev/projects/13590/badge"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
</p>

## Current status

Phases **0–3.5 are shipped**. **Phase 4 is in progress**: Track P operator readiness is the prerequisite for redesigned Track D capability slices. The current repository contains mounted, tenant-scoped, read-only **4.D.1 context/overview** and **4.D.2 metadata-only trace list/detail** surfaces. These are **mounted-but-provisional**, not proof of production identity, deployment, hosted acceptance, full management APIs, raw provenance, replay, or operator actions.

See the [status ledger](https://ibexharness.com/docs/architecture/status-and-evidence), [published benchmarks](https://ibexharness.com/benchmarks), [service inventory](services/README.md), [package inventory](packages/README.md), and [operator architecture boundary](engineering/OPERATOR_PLATFORM_ARCHITECTURE.md).

## Quick start

Prerequisites are Docker Compose v2 or Podman Compose, GNU Make, and the versions defined in [`infra/tool-versions.conf`](infra/tool-versions.conf). See [TOOLCHAIN.md](engineering/TOOLCHAIN.md).

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness

make setup
make check-tools
```

For a restricted sandbox or Podman machine:

```bash
IBEX_RUNTIME=podman IBEX_NETWORK=host make setup
```

Use `make env-doctor` for runtime, port, DNS, and injected telemetry diagnostics. `make db-seed` remains an optional local-development step; never run it against production.

For the complete setup, service startup matrix, test commands, and teardown procedure, read [DEVELOPMENT_GUIDE.md](engineering/DEVELOPMENT_GUIDE.md).

## Service and package navigation

| Area | Start here |
| --- | --- |
| Go AuthService | [services/auth/README.md](services/auth/README.md) |
| Go LLM proxy | [services/proxy/README.md](services/proxy/README.md) |
| Python management API | [services/api/README.md](services/api/README.md) |
| Python memory service | [services/memory/README.md](services/memory/README.md) |
| Context assembly | [services/context/README.md](services/context/README.md) |
| Embedder | [services/embedder/README.md](services/embedder/README.md) |
| MCP memory server | [services/mcp-memory/README.md](services/mcp-memory/README.md) |
| Celery workers | [services/worker/README.md](services/worker/README.md) |
| Canonical operator Console | [services/console/README.md](services/console/README.md) |
| Shared packages and protobuf | [packages/README.md](packages/README.md), [packages/proto/README.md](packages/proto/README.md) |
| Local infrastructure | [infra/README.md](infra/README.md) |

## Engineering and contribution docs

- [Architecture](engineering/ARCHITECTURE.md)
- [API documentation](engineering/API_DOCUMENTATION.md)
- [Environment variables](engineering/ENVIRONMENT_VARIABLES.md)
- [Security](engineering/SECURITY.md)
- [Testing strategy](engineering/TESTING_STRATEGY.md)
- [Contributing](CONTRIBUTING.md)

All status claims must distinguish **implemented**, **mounted-but-provisional**, **specified-not-implemented**, and **deferred**. Do not infer hosted readiness from local routes, fixtures, schemas, or design documents.
