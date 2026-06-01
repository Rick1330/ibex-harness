# Phase 0: Foundation

**Status:** Complete  
**Duration:** ~2 weeks (foundation audits 001–005 in session workspace archive)  
**Theme:** Documentation-first repo, governance, local infra, contracts, developer toolchain, honest service skeletons.

## Objectives

Establish a production-grade monorepo baseline before any product logic:

- Canonical docs and ADRs
- CI that enforces layout, markdown, and secrets
- Reproducible local dependencies (Compose)
- Protobuf contract source (Buf)
- Runnable Go services with health/readiness/metrics only

## Entry criteria

- Greenfield or docs-only repository

## Exit criteria (met)

- [x] `main` protected; required CI: `repo-guards`, `markdownlint`, `gitleaks`
- [x] `docs/` is source of truth for architecture, schema, APIs, security
- [x] `infra/compose/dev` and `infra/compose/test` validate in CI
- [x] `packages/proto` with Buf lint/breaking; generated code not committed
- [x] `Makefile` + `docs/TOOLCHAIN.md` + pre-commit hooks
- [x] `services/auth` and `services/proxy` skeletons; no business endpoints

## Artifacts

- [completed.md](completed.md) — deliverables and PR map
- [lessons-learned.md](lessons-learned.md) — retrospective for Phase 1+

## Next phase

[Phase 1: Core Platform](../phase-1-core-platform/README.md)
