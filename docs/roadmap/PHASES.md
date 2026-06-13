# Phases Overview

High-level roadmap from Foundation through production hardening. Detailed milestones for Phase 1 live under [phase-1-core-platform/](phase-1-core-platform/).

| Phase | Name | Est. duration | Status | Entry | Exit (summary) |
| --- | --- | --- | --- | --- | --- |
| [0](phase-0-foundation/) | Foundation | Done | **Complete** | Empty repo | CI, docs, compose, proto source, Go skeletons |
| [1](phase-1-core-platform/) | Core Platform | 4–6 weeks | **Complete** | Phase 0 complete | Migrations, auth, proxy platform, security gate |
| [1.5](phase-1-5-docs-site/) | Docs Site | 2–3 weeks | **In progress** | Phase 1 complete | Public docs at docs.ibexharness.com |
| [2](phase-2-single-provider/) | Single Provider E2E | 3–5 weeks | Planned | Phase 1.5 exit | Authenticated OpenAI-compatible chat through proxy |
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

**Status:** Complete

**Goals:** [goals.md](phase-1-core-platform/goals.md)

See [phase-1-core-platform/README.md](phase-1-core-platform/README.md) and [PHASE1_EXIT_AUDIT.md](phase-1-core-platform/PHASE1_EXIT_AUDIT.md).

---

## Phase 1.5: Docs Site

**Status:** In progress — current milestone [D.1.1](phase-1-5-docs-site/milestones/d1.1-pnpm-workspace-turborepo.md)

**Goals:** [phase-1-5-docs-site/goals.md](phase-1-5-docs-site/goals.md)

**Exit criteria:**

- Fumadocs site live at `https://docs.ibexharness.com`
- Matte Graphite design system; `verify_phase15.sh` passes
- Cross-links and sitemaps with landing site

---

## Phase 2: Single Provider E2E

**Status:** Planned — blocked on Phase 1.5 exit

**Goals:** [phase-2-single-provider/goals.md](phase-2-single-provider/goals.md)

| Goal | Summary |
| --- | --- |
| 2.1 | Provider abstraction and OpenAI forwarding (streaming + error mapping) |
| 2.2 | Auth LRU + bloom cache and revocation propagation |
| 2.3 | Directive resolution and system prompt injection |
| 2.4 | Session tracking and checkpoints |
| 2.5 | Async ClickHouse trace emission |
| 2.6 | Latency benchmark and Phase 2 exit gate |

**Exit criteria:**

- End-to-end chat completion via proxy to OpenAI (streaming and non-streaming)
- Proxy overhead <20ms p99; auth cache hit path <1ms
- Directive injected; sessions and ClickHouse traces emitted async
- Phase 1 security tests still pass; `make e2e-smoke` green

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
Phase 0 → Phase 1 → Phase 1.5 (docs) → Phase 2 provider → Phase 3 memory/context → Phase 4 scale → Phase 5 harden
```

Pivot triggers and discoveries: [FINDINGS.md](FINDINGS.md).
