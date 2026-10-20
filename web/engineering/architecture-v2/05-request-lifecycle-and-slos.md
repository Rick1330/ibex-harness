# Request Lifecycle, Deadlines, and SLOs

**Status:** `specified`; the proxy enforcement-overhead budget is ratified as a local/protected-profile target. Other numerical values remain targets, and none is a hosted measurement.

## Lifecycle

```text
validate → authenticate → verify agent/resource → policy snapshot
→ rate/concurrency → durable reservation → capability/token fit
→ authorized context compile → provider call/stream
→ usage reconciliation → evidence acceptance → response
```

The provider must not be called after a security, policy, capability, reservation, or evidence-integrity denial.

## Timing policy

The former documents contain incompatible 20 ms, 40 ms, 45 ms, 50 ms, and 100 ms claims. This document now ratifies one proxy budget and keeps the remaining values explicitly separate:

- **Proxy enforcement overhead (ratified local/protected-profile target): p99 ≤20 ms.** The SLI is request accept to response headers returned to the caller, measured with a mock provider, warm auth/rate-limit/directive caches, context assembly disabled, and the full-chat k6 profile. It excludes provider time, post-header stream time, cold-cache behavior, and hosted/reference performance. ADR-0034 and `benchmarks/data-schema/baseline.json` use the same ceiling.
- **Context RPC deadline: 40 ms internal client timeout.** This is not an SLO and must not be folded into the proxy-overhead budget.
- **Context compilation: p95 ≤50 ms / p99 ≤100 ms are targets pending measurement.** They are not ratified SLOs until a workload-qualified benchmark is published.
- Provider first byte, stream tail, and total platform-added latency: separate SLIs.

The proxy budget has two evidence layers: a blocking PR-time relative Go benchmark gate (warm-path means against a same-runner `main` baseline, 20% tolerance) and scheduled/manual full-chat k6 runs as the intended p99 evidence path. The Go gate is not p99 evidence and does not prove hosted performance. Published history currently contains no recent passing full-chat p99 run, so this remains an owned target rather than a measured production SLO.

Every future measurement must publish workload, model/tokenizer, tenant size, warm/cold state, concurrency, hardware, queue time, error policy, and artifact/config digests.

## Synchronous versus asynchronous

Synchronous: identity, scope, policy, reservation, deterministic capability/token checks, bounded context, provider call/stream, and minimum durable admission acceptance.
Asynchronous: extraction, deep PII, optional embeddings, reranking, conflict proposals, drift, analytics projections, notifications, and large artifacts.

## Safe degradation

Quality dependencies may produce directive-only or verified hot-cache context. Security/integrity dependencies produce deny/no-route/503. Every degraded response carries a machine-readable reason and evidence linkage.
