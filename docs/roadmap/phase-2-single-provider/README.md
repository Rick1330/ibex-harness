# Phase 2: Single Provider E2E

**Status:** Planned  
**Estimated duration:** 3–5 weeks  
**Depends on:** [Phase 1 exit criteria](../phase-1-core-platform/README.md)

## Theme

Prove the **critical path** end-to-end: authenticated agent → proxy → LLM provider → streamed response, with async trace emission and fail-closed auth.

## Why this phase matters

Phase 1 wires auth and normalizes requests without calling a provider. Phase 2 validates latency budgets, streaming, and operational patterns before investing in memory/context complexity.

## Entry criteria

- Phase 1 complete (migrations, auth validate, proxy auth middleware, request normalization)
- Local compose stack healthy

## Exit criteria

- Proxy forwards chat completion requests to **one** OpenAI-compatible provider
- Streaming responses pass through without buffering entire body on hot path
- Invalid/missing auth returns stable error envelope (401/403 per API docs)
- Traces/metrics for proxy stages; ClickHouse write is async
- Integration test with mocked provider or recorded HTTP fixtures

## Goals

See [goals.md](goals.md).

## Milestones

Detailed milestone files will be added when Phase 1 exits. Expected areas:

- Provider HTTP client + timeouts
- Streaming mux to client
- Error mapping from provider to stable API shape
- Basic org-level rate limit in Redis (optional)

## Risks

- Provider API drift vs documented OpenAI shape
- Streaming backpressure under slow clients
- Secret handling for provider API keys (env + never log)

See Phase 1 [risks.md](../phase-1-core-platform/risks.md) for shared platform risks.
