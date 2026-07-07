<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Rick1330/ibexharness-benchmark-bot/main/docs/brand/ibex-mark-dark.png">
    <img alt="IBEX Harness" src="https://raw.githubusercontent.com/Rick1330/ibexharness-benchmark-bot/main/docs/brand/ibex-mark-light.png" width="96" height="96">
  </picture>
</p>

<h1 align="center">IBEX Harness</h1>

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

## Quick start

- **Prerequisites**: Docker, Go, Buf, Make. See `docs/TOOLCHAIN.md`.
- **Full setup and local workflow**: `docs/DEVELOPMENT_GUIDE.md`.

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness

make compose-dev-up
make db-migrate
make db-seed
```

## What to read next

- **Architecture**: `docs/ARCHITECTURE.md`
- **Environment variables**: `docs/ENVIRONMENT_VARIABLES.md`
- **Contributing**: `CONTRIBUTING.md`
