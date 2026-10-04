# Request Lifecycle, Deadlines, and SLOs

**Status:** `specified` with numerical values as `target`, not measured results.

## Lifecycle

```text
validate → authenticate → verify agent/resource → policy snapshot
→ rate/concurrency → durable reservation → capability/token fit
→ authorized context compile → provider call/stream
→ usage reconciliation → evidence acceptance → response
```

The provider must not be called after a security, policy, capability, reservation, or evidence-integrity denial.

## Timing policy

The former documents contain incompatible 20 ms, 40 ms, 45 ms, 50 ms, and 100 ms claims. The interim target is:

- Enforcement overhead: **target p99 ≤20 ms**, excluding provider time and separately reporting context.
- Context RPC deadline: **one approved 40 ms deadline**, pending benchmark confirmation.
- Context compilation: separate p50/p95/p99 SLI; no guarantee until measured.
- Provider first byte, stream tail, and total platform-added latency: separate SLIs.

These are targets. A benchmark must publish workload, model/tokenizer, tenant size, warm/cold state, concurrency, hardware, queue time, error policy, and artifact/config digests.

## Synchronous versus asynchronous

Synchronous: identity, scope, policy, reservation, deterministic capability/token checks, bounded context, provider call/stream, and minimum durable admission acceptance.
Asynchronous: extraction, deep PII, optional embeddings, reranking, conflict proposals, drift, analytics projections, notifications, and large artifacts.

## Safe degradation

Quality dependencies may produce directive-only or verified hot-cache context. Security/integrity dependencies produce deny/no-route/503. Every degraded response carries a machine-readable reason and evidence linkage.
