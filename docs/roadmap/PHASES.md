# Phases Overview

High-level roadmap from Foundation through production hardening. Detailed milestones for Phase 1 live under [phase-1-core-platform/](phase-1-core-platform/).

| Phase | Name | Est. duration | Status | Entry | Exit (summary) |
| --- | --- | --- | --- | --- | --- |
| [0](phase-0-foundation/) | Foundation | Done | **Complete** | Empty repo | CI, docs, compose, proto source, Go skeletons |
| [1](phase-1-core-platform/) | Core Platform | 4–6 weeks | **In Progress** | Phase 0 complete | Migrations, auth validate, proxy auth wire-up, observability baseline |
| [2](phase-2-single-provider/) | Single Provider E2E | 3–5 weeks | Planned | Phase 1 exit | Authenticated OpenAI-compatible chat through proxy |
| [3](phase-3-context-system/) | Context and Memory | 6–8 weeks | Planned | Phase 2 exit | Memory CRUD, embeddings, context assembly, injection |
| [4](phase-4-multi-provider/) | Multi-Provider and Routing | 4–6 weeks | Planned | Phase 3 exit | Multiple providers, routing, Redis rate limits |
| [5](phase-5-production-hardening/) | Production Hardening | 4–8 weeks | Planned | Phase 4 exit | SLOs, OTel pipeline, chaos/load, required Go CI |

---

## Phase 0: Foundation

**Status:** Complete

**Delivered:** Documentation-first monorepo, governance CI, Buf proto foundation, local compose, toolchain (`Makefile`, `TOOLCHAIN.md`), Go auth/proxy skeletons with health/readiness/metrics.

**Merge commits:** `c4d302a` (toolchain), `5d0bfac` (Go skeletons).

See [phase-0-foundation/README.md](phase-0-foundation/README.md).

---

## Phase 1: Core Platform

**Status:** In Progress — starting Milestone 1.1.1

**Goals:** [goals.md](phase-1-core-platform/goals.md)

| Goal | Summary |
| --- | --- |
| 1.1 | Persistence and auth data plane (migrations, auth proto, token validation) |
| 1.2 | Proxy platform integration (auth client, request normalization) |
| 1.3 | Observability baseline (OTel wiring, Prometheus client) |

**Exit criteria:**

- `make db-migrate` applies minimal auth schema; idempotent re-run
- Auth validates org tokens against Postgres; cross-tenant tests pass
- Proxy rejects unauthenticated requests; normalizes OpenAI-shaped bodies (no upstream yet)
- Structured logs + metrics on critical paths; OTel tracer provider wired (no exporter required)

---

## Phase 2: Single Provider E2E

**Status:** Planned

**Goals:** [phase-2-single-provider/goals.md](phase-2-single-provider/goals.md)

**Exit criteria:**

- End-to-end chat completion via proxy to one provider (OpenAI-compatible)
- Streaming responses forwarded to client
- Traces/metrics emitted async; no sync analytics on hot path
- Rate limit skeleton or basic org-level limit in Redis (optional milestone)

---

## Phase 3: Context and Memory

**Status:** Planned

**Goals:** [phase-3-context-system/goals.md](phase-3-context-system/goals.md)

**Exit criteria:**

- Memory service: CRUD + vector search with tenant isolation
- Context assembly implements `ContextAssemblyService` proto
- Proxy injects assembled context on LLM calls within latency budget
- Workers: extraction job enqueued async from proxy

---

## Phase 4: Multi-Provider and Routing

**Status:** Planned

**Goals:** [phase-4-multi-provider/goals.md](phase-4-multi-provider/goals.md)

**Exit criteria:**

- Provider adapter interface; at least two providers
- Model routing and failover policies
- Production-grade Redis rate limiting (Lua)
- Streaming backpressure hardened

---

## Phase 5: Production Hardening

**Status:** Planned

**Goals:** [phase-5-production-hardening/goals.md](phase-5-production-hardening/goals.md)

**Exit criteria:**

- OTel collectors and Grafana dashboards per MONITORING.md
- Circuit breakers on external deps; documented fallbacks
- Load/chaos tests on proxy path
- Promote `go-services` / `golangci-lint` to required checks when stable

---

## Critical path (dependency order)

```text
Phase 0 → Migrations → Auth proto → Auth validate → Proxy auth → Proxy normalize
       → Phase 2 provider → Phase 3 memory/context → Phase 4 scale → Phase 5 harden
```

Pivot triggers and discoveries: [FINDINGS.md](FINDINGS.md).
