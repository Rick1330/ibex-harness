# Phase 2: Single Provider E2E

**Status:** Planned
**Estimated duration:** 3–5 weeks
**Depends on:** [Phase 1 exit criteria](../phase-1-core-platform/README.md)
**Current milestone:** [2.3.1 Directive migrations](milestones/2.3.1-directive-migrations.md) (after Phase 1 completes)

## Purpose

Phase 2 transforms IBEX Harness from a security-complete authentication and rate limiting layer (Phase 1) into a **working AI proxy** — one that receives a real LLM request, optionally enriches it with an agent directive, forwards it to OpenAI, streams the response back to the caller, and emits an async trace to ClickHouse for analytics.

At the end of Phase 2, a customer can point their OpenAI SDK at the IBEX proxy endpoint, configure an agent directive, and every request will be transparently enriched, authenticated, rate-limited, traced, and forwarded. This is the first deployable product milestone.

## Milestones

| ID | Milestone | Status |
| --- | --- | --- |
| 2.1.1 | [Provider interface and registry](milestones/2.1.1-provider-interface-and-registry.md) | Planned |
| 2.1.2 | [OpenAI non-streaming client](milestones/2.1.2-openai-non-streaming-client.md) | Planned |
| 2.1.3 | [OpenAI streaming forwarder](milestones/2.1.3-openai-streaming-forwarder.md) | Planned |
| 2.1.4 | [Provider routing middleware](milestones/2.1.4-provider-routing-middleware.md) | Planned |
| 2.1.5 | [Provider error mapping](milestones/2.1.5-provider-error-mapping.md) | Planned |
| 2.2.1 | [Auth cache bloom + LRU](milestones/2.2.1-auth-cache-bloom.md) | Planned |
| 2.2.2 | [Token revocation propagation](milestones/2.2.2-token-revocation-propagation.md) | Planned |
| 2.3.1 | [Directive migrations](milestones/2.3.1-directive-migrations.md) | Planned |
| 2.3.2 | [Directive resolver](milestones/2.3.2-directive-resolver.md) | Planned |
| 2.3.3 | [System prompt injection](milestones/2.3.3-system-prompt-injection.md) | Planned |
| 2.4.1 | [Sessions and checkpoints migrations](milestones/2.4.1-sessions-checkpoints-migrations.md) | Planned |
| 2.4.2 | [Session store](milestones/2.4.2-session-store.md) | Planned |
| 2.4.3 | [Proxy session lifecycle](milestones/2.4.3-proxy-session-lifecycle.md) | Planned |
| 2.5.1 | [ClickHouse schema](milestones/2.5.1-clickhouse-schema.md) | Planned |
| 2.5.2 | [ClickHouse client](milestones/2.5.2-clickhouse-client.md) | Planned |
| 2.5.3 | [Async trace emitter](milestones/2.5.3-async-trace-emitter.md) | Planned |
| 2.6.1 | [Latency benchmark](milestones/2.6.1-latency-benchmark.md) | Planned |
| 2.6.2 | [Phase 2 exit gate](milestones/2.6.2-phase2-exit-gate.md) | Planned |

## What Phase 2 is not

Phase 2 intentionally excludes:

- **Memory injection** — agents won't have persistent memory yet (Phase 3). Directives are static.
- **Multi-provider routing** — only OpenAI in Phase 2 (Phase 4 adds Anthropic, Bedrock, etc.)
- **Dashboard or API server** — operator UI is Phase 3
- **Embedding service** — not needed without memory
- **Hierarchical rate limiting** — Lua-script atomic rate limiter with per-agent limits (Phase 4)
- **Billing integration** — token counting is tracked but not charged (Phase 3)

## Critical path

```text
Client SDK
    │
    ▼  POST /v1/chat/completions
┌─────────────────────────────────────────────────────────┐
│                      IBEX Proxy                         │
│  RequestID → Auth (LRU cache) → AgentVerify → RateLimit │
│  → DirectiveResolver → PromptInjector                   │
│  → OpenAI HTTP Client                                   │
│  → SSE Stream Forward (dual-write)                      │
│  → [async] Session checkpoint + Trace emit              │
└─────────────────────────────────────────────────────────┘
    │
    ▼  SSE stream
Client SDK
```

**Latency budget at Phase 2:**

| Stage | Budget |
| --- | --- |
| Auth (LRU cache hit) | <1ms |
| Auth (gRPC fallback on miss) | <50ms |
| Agent verification (LRU cache hit) | <1ms |
| Rate limit (Redis INCR) | <5ms |
| Directive resolve (Redis cache hit) | <2ms |
| Prompt injection | <0.5ms |
| Total proxy overhead (non-provider) | <20ms (p99 target) |
| OpenAI TTFB | varies (not in our control) |

## Entry criteria

- Phase 1 complete (including [M1.5.1](../phase-1-core-platform/milestones/1.5.1-security-integration-test-suite.md) security gate)
- [Phase 1.5](../phase-1-5-docs-site/README.md) docs site launched at `docs.ibexharness.com` (docs-first sequencing)
- Local compose stack healthy (Postgres, Redis; ClickHouse added in 2.5.1)

## Exit criteria

Phase 2 is complete when ALL of the following are true:

1. `POST /v1/chat/completions` with a valid PAT and agent directive returns a real OpenAI completion
2. Streaming mode: first bytes arrive at client within 100ms of provider TTFB
3. Proxy overhead (non-provider time) is <20ms at p99 under 100 concurrent requests
4. Directive is correctly prepended to the system message in every request
5. Every request creates or updates a session checkpoint in Postgres
6. Every completed request emits a trace to ClickHouse within 500ms of response completion
7. Token revocation is reflected in the auth cache within 5 seconds
8. All Phase 1 security tests (milestone 1.5.1) still pass with no regressions
9. `make e2e-smoke` (Phase 2 smoke test with OpenAI sandbox key) exits 0

## Execution order

```text
2.3.1 (directive migrations)
  → 2.4.1 (session migrations)
  → 2.5.1 (ClickHouse schema)
      [these three can run in parallel — all are schema/infra]

2.2.1 (auth LRU cache) → 2.2.2 (revocation propagation)

2.3.2 (directive resolver) → 2.3.3 (prompt injection)

2.1.1 (provider interface)
  → 2.1.2 (OpenAI non-streaming)
  → 2.1.3 (OpenAI streaming)
  → 2.1.4 (provider routing)
  → 2.1.5 (provider error mapping)

2.4.2 (session store) → 2.4.3 (proxy session lifecycle)
2.5.2 (ClickHouse client) → 2.5.3 (async trace emitter)

[all above merged]
2.6.1 (latency benchmark) → 2.6.2 (Phase 2 exit gate)
```

## Documents

- [goals.md](goals.md) — Goals 2.1–2.6
- [milestones/](milestones/) — PR-sized work units
- [decisions.md](decisions.md) — Phase-local decision log
- [risks.md](risks.md) — Risks and mitigations

## Goal overview

| Goal | Focus |
| --- | --- |
| [2.1](goals.md#goal-21-llm-provider-abstraction-and-openai-forwarding) | Provider abstraction and OpenAI forwarding |
| [2.2](goals.md#goal-22-auth-performance-cache-critical-path) | Auth LRU + bloom cache |
| [2.3](goals.md#goal-23-directive-resolution-and-prompt-injection) | Directive resolve and inject |
| [2.4](goals.md#goal-24-session-tracking-infrastructure) | Sessions and checkpoints |
| [2.5](goals.md#goal-25-async-trace-emission-to-clickhouse) | ClickHouse async traces |
| [2.6](goals.md#goal-26-phase-2-quality-gate--latency-and-load) | Latency benchmark and exit gate |

## Next phase

When exit criteria are met, begin [Phase 3: Context and Memory](../phase-3-context-system/README.md).
