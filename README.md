<p align="center">
  <img src="./ibex-mark.png" width="96" height="96" alt="IBEX Harness">
</p>

<h2 align="center">IBEX Harness</h2>

<p align="center">
  Production-grade platform for AI agent memory, context assembly, and secure LLM proxying.
</p>

<p align="center">
  <a href="https://docs.ibexharness.com">Docs</a>
  · <a href="https://docs.ibexharness.com/benchmarks">Benchmarks</a>
  · <a href="docs/DEVELOPMENT_GUIDE.md">Developer guide</a>
  · <a href="docs/SECURITY.md">Security</a>
</p>

<p align="center">
  <a href="https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://codecov.io/gh/Rick1330/ibex-harness"><img alt="codecov" src="https://codecov.io/gh/Rick1330/ibex-harness/graph/badge.svg"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
</p>

## Quick start (local dev)

- **Prerequisites**: Docker, Go, Buf, Make. See `docs/TOOLCHAIN.md`.
- **Full setup & workflow**: `docs/DEVELOPMENT_GUIDE.md`.

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness

make compose-dev-up
make db-migrate
make db-seed

cp services/auth/.env.example services/auth/.env
cp services/proxy/.env.example services/proxy/.env

go run ./services/auth/cmd/auth
# in another terminal
IBEX_AUTH_VALIDATE_TIMEOUT=2s go run ./services/proxy/cmd/proxy
```

## What to read next

- **Architecture**: `docs/ARCHITECTURE.md`
- **Environment variables**: `docs/ENVIRONMENT_VARIABLES.md`
- **Contributing**: `CONTRIBUTING.md`

