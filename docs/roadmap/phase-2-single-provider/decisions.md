# Phase 2 — Decision Log

Quick decisions during Phase 2. Promote durable choices to `docs/adr/` when they affect multiple phases.

| Date | Decision | Rationale | ADR |
| --- | --- | --- | --- |
| TBD | LLM provider abstraction (`provider.Provider`, registry) | Phase 4 multi-provider without rewriting proxy handlers | [ADR-0022](../../adr/ADR-0022-llm-provider-abstraction.md) — **Pending** |
| TBD | OpenAI HTTP client, pooling, retry policy | Production-grade forwarding for first provider | [ADR-0023](../../adr/ADR-0023-openai-client-design.md) — **Pending** |
| TBD | Streaming dual-write and backpressure | Real-time SSE without buffering full body on hot path | [ADR-0024](../../adr/ADR-0024-streaming-dual-write.md) — **Pending** |
| TBD | Auth LRU + bloom filter cache | Meet <20ms proxy overhead under load | [ADR-0025](../../adr/ADR-0025-auth-cache-design.md) — **Pending** |
| TBD | Token revocation propagation SLA | Cache correctness vs performance (5s Phase 2 target) | [ADR-0026](../../adr/ADR-0026-revocation-propagation.md) — **Pending** |
| TBD | Directive immutable versioning | Safe cache invalidation without lost updates | [ADR-0027](../../adr/ADR-0027-directive-versioning.md) — **Pending** |
| TBD | System prompt injection ordering | Directive precedes caller system message | [ADR-0028](../../adr/ADR-0028-system-prompt-injection.md) — **Pending** |
| TBD | Session and checkpoint data model | Foundation for Phase 3 memory extraction | [ADR-0029](../../adr/ADR-0029-session-data-model.md) — **Pending** |
| TBD | ClickHouse trace schema and retention | Analytics backbone without hot-path blocking | [ADR-0030](../../adr/ADR-0030-clickhouse-schema.md) — **Pending** |
| TBD | Proxy overhead measurement methodology | Reproducible p99 benchmark for exit gate | [ADR-0031](../../adr/ADR-0031-performance-methodology.md) — **Pending** |
| 2026-06-05 | Auth cache required in Phase 2 (not optional) | Phase 2 latency budget impossible with per-request gRPC only | See [phase-1 decisions](../phase-1-core-platform/decisions.md) |

## Pending decisions (resolve during milestones)

1. **OpenAI API base URL** — default `https://api.openai.com/v1`; document override for Azure in Phase 4.
2. **ClickHouse deployment in dev** — compose service vs external; document in `ENVIRONMENT_VARIABLES.md` at 2.5.2.
3. **E2E smoke OpenAI key** — sandbox key in CI secrets vs skipped required check (resolve in 2.6.2).

Log pivots in [FINDINGS.md](../FINDINGS.md).
