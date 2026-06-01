# Phase 1: Core Platform

**Status:** In Progress  
**Estimated duration:** 4–6 weeks  
**Current milestone:** [1.1.1 Postgres migrations](milestones/1.1.1-postgres-migrations.md)

## Theme

Build the **platform layer** required before any LLM provider call: durable schema, auth validation, proxy authentication wiring, request normalization, and observability baseline.

## Why this phase matters

Foundation-004 delivered honest skeletons. Phase 1 turns them into a **fail-closed platform**: tokens validated against Postgres, proxy rejects unauthenticated traffic, requests parsed into a stable internal shape—without yet calling OpenAI or implementing memory.

## Entry criteria

- [x] Phase 0 complete (`main` includes toolchain, compose, proto source, Go skeletons)
- [x] `make compose-dev-up` brings Postgres/Redis healthy
- [x] Required CI green on `main`

## Exit criteria

- [ ] `make db-migrate` applies minimal `ibex_core` schema; second run is no-op
- [ ] Auth service validates organization API tokens (PAT) via gRPC; Argon2id verify; permission bitmap returned
- [ ] Auth and proxy cross-tenant integration tests pass
- [ ] Proxy middleware rejects missing/invalid auth before handler logic
- [ ] Proxy parses OpenAI-compatible chat request JSON into internal struct (no upstream HTTP)
- [ ] OTel tracer provider registered (noop exporter OK); Prometheus via official client or migration plan executed
- [ ] ADR-0005 (migrations), ADR-0006 (auth proto) accepted
- [ ] `docs/roadmap/CURRENT_STATE.md` updated at phase exit

## Dependencies

| Dependency | Notes |
| --- | --- |
| Docker Compose dev stack | Postgres 16 + pgvector image already in compose |
| Buf | For auth proto in milestone 1.1.2 |
| golang-migrate (or ADR-chosen tool) | Milestone 1.1.1 |

## Documents

- [goals.md](goals.md) — Goals 1.1–1.3
- [milestones/](milestones/) — PR-sized work units
- [decisions.md](decisions.md) — Phase-local decision log
- [risks.md](risks.md) — Risks and mitigations

## Goal overview

| Goal | Focus |
| --- | --- |
| [1.1](goals.md#goal-11-persistence-and-auth-data-plane) | Migrations, auth proto, token validation |
| [1.2](goals.md#goal-12-proxy-platform-integration) | Proxy auth client, request normalization |
| [1.3](goals.md#goal-13-observability-baseline) | OTel + Prometheus client |

## Next phase

When exit criteria are met, begin [Phase 2: Single Provider E2E](../phase-2-single-provider/README.md).
