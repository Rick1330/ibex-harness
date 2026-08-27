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
  <a href="https://ibexharness.com">Docs</a>
  · <a href="https://ibexharness.com/benchmarks">Benchmarks</a>
  · <a href="web/engineering/DEVELOPMENT_GUIDE.md">Developer guide</a>
  · <a href="web/engineering/SECURITY.md">Security</a>
</p>

<p align="center">
  <a href="https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Rick1330/ibex-harness/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://codecov.io/gh/Rick1330/ibex-harness"><img alt="codecov" src="https://codecov.io/gh/Rick1330/ibex-harness/graph/badge.svg"></a>
  <a href="https://scorecard.dev/viewer/?uri=github.com/Rick1330/ibex-harness&platform=github.com"><img alt="OpenSSF Scorecard" src="https://api.securityscorecards.dev/projects/github.com/Rick1330/ibex-harness/badge"></a>
  <a href="https://www.bestpractices.dev/projects/13590"><img alt="OpenSSF Best Practices" src="https://www.bestpractices.dev/projects/13590/badge"></a>
  <a href="https://www.bestpractices.dev/projects/13590"><img alt="OpenSSF Baseline" src="https://www.bestpractices.dev/projects/13590/baseline"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
</p>

## Current status

Phases **0–2.5 are complete** (auth, multi-provider proxy, tokenizer, response pipeline, embedder, MCP skeleton, local LGTM). **Phase 3** (Core Memory Substrate) is in progress: schema v2 / HNSW, VectorStore, PII, exact/near dedup, and temporal conflict detection on the write path. Next after Track C: classify (3.C.4), then Track D read path. Extraction/context assembly are Phase **3.5**; operator platform is Phase **4**; intelligence is Phase **4.5**; advanced retrieval is Phase **5**. See [roadmap current state](https://ibexharness.com/roadmap/current-state).

## Quick start

- **Prerequisites**: Docker, Go, Buf, Make, Node 22 / pnpm 9. See [TOOLCHAIN.md](web/engineering/TOOLCHAIN.md).
- **Full setup and local workflow**: [DEVELOPMENT_GUIDE.md](web/engineering/DEVELOPMENT_GUIDE.md).

```bash
git clone https://github.com/Rick1330/ibex-harness.git
cd ibex-harness

make compose-dev-up
make db-migrate
make db-seed
```

## What to read next

- **Architecture**: [ARCHITECTURE.md](web/engineering/ARCHITECTURE.md)
- **Environment variables**: [ENVIRONMENT_VARIABLES.md](web/engineering/ENVIRONMENT_VARIABLES.md)
- **Contributing**: [CONTRIBUTING.md](CONTRIBUTING.md) — see [Good first issues](CONTRIBUTING.md#good-first-issues) for beginner-friendly tasks
- **API reference**: [ibexharness.com/docs/api-reference/chat-completions](https://ibexharness.com/docs/api-reference/chat-completions) (REST + gRPC interfaces)
- **OpenSSF Best Practices**: [OPENSSF_BEST_PRACTICES.md](web/engineering/OPENSSF_BEST_PRACTICES.md)
