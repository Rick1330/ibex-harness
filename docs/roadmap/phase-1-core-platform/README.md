# Phase 1: Core Platform

**Status:** In Progress  
**Estimated duration:** 4–6 weeks  
**Current milestone:** [1.2.2 Proxy request normalization](milestones/1.2.2-proxy-request-normalization.md)

## Milestones

| ID | Milestone | Status |
| --- | --- | --- |
| 1.0.1 | [Go integration test infrastructure](milestones/1.0.1-go-integration-test-infrastructure.md) | Complete |
| 1.1.1 | [Postgres migrations](milestones/1.1.1-postgres-migrations.md) | Complete |
| 1.1.2 | [Auth proto and codegen](milestones/1.1.2-auth-proto-and-codegen.md) | Complete |
| 1.1.3 | [Auth token validation](milestones/1.1.3-auth-token-validation.md) | Complete |
| 1.1.4 | [Token creation and management API](milestones/1.1.4-token-creation-and-management-api.md) | Complete |
| 1.1.5 | [Permission bitmap contract and ADR](milestones/1.1.5-permission-bitmap-contract-and-adr.md) | Complete |
| 1.1.6 | [Argon2id parameters and crypto policy ADR](milestones/1.1.6-argon2id-parameters-and-crypto-policy-adr.md) | Complete |
| 1.2.1 | [Proxy auth client](milestones/1.2.1-proxy-auth-client.md) | Complete |
| 1.2.2 | [Proxy request normalization](milestones/1.2.2-proxy-request-normalization.md) | In progress (PR) |
| 1.2.3 | [Proxy input validation and error envelope](milestones/1.2.3-proxy-input-validation-and-stable-error-envelope.md) | Next |
| 1.2.4 | [Proxy rate limit skeleton](milestones/1.2.4-proxy-rate-limit-skeleton.md) | Planned |
| 1.3.1 | [Observability baseline](milestones/1.3.1-observability-baseline.md) | Planned |

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

- [goals.md](goals.md) — Goals 1.0–1.3
- [milestones/](milestones/) — PR-sized work units
- [decisions.md](decisions.md) — Phase-local decision log
- [risks.md](risks.md) — Risks and mitigations

## Goal overview

| Goal | Focus |
| --- | --- |
| [1.0](goals.md#goal-10-test-infrastructure-prerequisite) | Integration test harness (optional before heavy integration work) |
| [1.1](goals.md#goal-11-persistence-and-auth-data-plane) | Migrations, auth proto, token validation, token API backlog |
| [1.2](goals.md#goal-12-proxy-platform-integration) | Proxy auth client, normalization, validation, rate limits |
| [1.3](goals.md#goal-13-observability-baseline) | OTel + Prometheus client |

## Next phase

When exit criteria are met, begin [Phase 2: Single Provider E2E](../phase-2-single-provider/README.md).
