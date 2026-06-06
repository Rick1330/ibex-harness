# Phase 2 — Risks and Mitigations

| Risk | Area | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- | --- |
| Provider API drift vs OpenAI schema | 2.1.x | Medium | High | Contract tests with recorded fixtures; pin API version header |
| Streaming backpressure under slow clients | 2.1.3 | Medium | High | Context cancellation; dual-write buffer limits per ADR-0024 |
| Auth cache serves revoked token | 2.2.x | Medium | Critical | 2.2.2 revocation propagation; integration tests per TESTING_STRATEGY |
| Bloom filter false positives reject valid token | 2.2.1 | Low | Medium | Document false-positive rate; gRPC fallback on bloom hit |
| Directive cache stale after update | 2.3.x | Medium | Medium | Versioned keys; sub-second invalidation on write |
| Session write blocks response path | 2.4.x | Low | High | Async checkpoint after response complete |
| ClickHouse outage affects LLM responses | 2.5.x | Low | Critical | Async emitter; failures logged only, never fail request |
| Proxy overhead regression from Phase 2 features | 2.6.x | Medium | High | 2.6.1 benchmark gate before 2.6.2 exit |
| OpenAI rate limits during load test | 2.6.x | Medium | Low | Mock provider for CI; real key only in optional smoke |
| Phase 1 security regression | 2.6.2 | Low | Critical | Re-run M1.5.1 suite as Phase 2 exit criterion |

See [phase-1 risks](../phase-1-core-platform/risks.md) for shared platform risks (RLS, secrets, CI).
