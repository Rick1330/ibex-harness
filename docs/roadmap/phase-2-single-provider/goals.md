# Phase 2 — Goals

## Goal 2.1: LLM Provider Abstraction and OpenAI Forwarding

**What:** A provider abstraction layer in the proxy that enables routing requests to a real LLM provider. Phase 2 implements OpenAI (the most widely used provider) as the first concrete implementation.

**Why this goal exists:** Phase 1 built the security and rate limiting infrastructure, but the proxy does not forward any request anywhere — every request returns `501 Provider Not Configured`. Phase 2 makes the proxy actually useful.

**Acceptance criteria:**
- `POST /v1/chat/completions` (non-streaming) returns a valid OpenAI response when `stream=false`
- `POST /v1/chat/completions` (streaming) forwards SSE tokens in real time when `stream=true`
- Provider errors (OpenAI 429, 500, 503) are mapped to the stable IBEX error envelope
- Provider API keys are stored in environment variables, never in Postgres or Redis
- No provider API key or response content appears in logs, metrics labels, or trace attributes

**Milestones:** 2.1.1 → 2.1.2 → 2.1.3 → 2.1.4 → 2.1.5

---

## Goal 2.2: Auth Performance Cache (Critical Path)

**What:** Replace the per-request gRPC `ValidateToken` call with a two-tier cache: an in-process LRU for validated token claims, backed by a Redis bloom filter for fast rejection of invalid tokens.

**Why this goal exists:** The Phase 1 proxy makes a synchronous gRPC call to auth on every request. This call has a 50ms budget and under load will consume 50ms of the 20ms proxy overhead target — a physical impossibility. The auth cache reduces the hot-path auth check to <1ms for recently seen valid tokens.

**Acceptance criteria:**
- Cache hit path requires no network call; measured latency <1ms
- Cache miss falls back to gRPC (existing Phase 1 path)
- Revoked token rejected within 5 seconds of revocation (SLA for Phase 2)
- Token cache entries expire before the token's own `expires_at`
- No token values (raw or hashed) appear as Prometheus label values or log field values

**Milestones:** 2.2.1 → 2.2.2

---

## Goal 2.3: Directive Resolution and Prompt Injection

**What:** Every agent can have a "directive" — a system-level instruction that is injected into every LLM request made by that agent. The proxy resolves the directive from a Redis cache (backed by Postgres) and injects it into the messages array before forwarding to the provider.

**Why this goal exists:** This is the first content-level value add of IBEX Harness beyond authentication. Without directive injection, the proxy is just an authenticated HTTP proxy. With it, operators can define agent personas, safety constraints, and behavioural guidelines that are transparently enforced on every LLM call — even if the calling application doesn't think about them.

**Acceptance criteria:**
- Agent directive is resolved from Redis cache within 2ms (warm path)
- Directive is injected as the first system message in the messages array
- If an existing system message is present, it follows the directive (not replaced)
- Directive cache is invalidated within 1 second of a directive update
- Requests to agents with no directive set work correctly (no injection)
- Directive content is NOT logged or included in trace attributes (privacy)

**Milestones:** 2.3.1 → 2.3.2 → 2.3.3

---

## Goal 2.4: Session Tracking Infrastructure

**What:** Every LLM conversation (a series of turns between a user and an agent) is tracked as a "session." Each request within a session creates a "checkpoint" — a snapshot of the turn's input and output token counts, latency, and model used.

**Why this goal exists:** Sessions are the foundational data structure for Phase 3 memory extraction. Without session tracking, the proxy has no durable record of conversations to extract memories from. Additionally, sessions are the billing unit in Phase 3 — you cannot bill by conversation without knowing where conversations start and end.

**Acceptance criteria:**
- A session is created in Postgres on the first request that carries `X-IBEX-Session-ID` or omits it (auto-created)
- A checkpoint is created for every completed turn (both streaming and non-streaming)
- Checkpoint includes: turn index, input token count, output token count, model, latency ms, provider
- Session creation and checkpoint writes do not block the response path (async after response sent)
- Sessions are correctly scoped to (org_id, agent_id) — cross-tenant access is impossible

**Milestones:** 2.4.1 → 2.4.2 → 2.4.3

---

## Goal 2.5: Async Trace Emission to ClickHouse

**What:** After every completed LLM request, the proxy emits a structured trace record to ClickHouse — a columnar analytics database designed for high-throughput append-only writes. The trace record captures latency breakdown by stage, token usage, model, and request metadata.

**Why this goal exists:** ClickHouse is the analytics backbone of IBEX Harness. The Phase 3 dashboard, the billing engine, and the drift detection system all query ClickHouse. Starting trace emission in Phase 2 means that by the time Phase 3 ships, there is already accumulated operational data to work with. Delaying trace emission to Phase 3 would mean the dashboard launches with zero historical data.

**The non-blocking requirement is absolute:** A ClickHouse write failure must never fail an LLM response. The trace is observability infrastructure — its failure is advisory, not critical.

**Acceptance criteria:**
- Trace is emitted asynchronously after response completes (not before)
- ClickHouse write failure does not affect LLM response status
- Trace includes: request_id, org_id, agent_id, session_id, model, provider, input_tokens, output_tokens, ttfb_ms, total_latency_ms, proxy_overhead_ms
- Trace is visible in ClickHouse within 500ms of response completion under normal load
- No LLM response content (prompt or completion) is stored in ClickHouse traces

**Milestones:** 2.5.1 → 2.5.2 → 2.5.3

---

## Goal 2.6: Phase 2 Quality Gate — Latency and Load

**What:** A benchmark and load test suite that proves the proxy meets its <20ms overhead target and confirms no performance regression from Phase 2 additions (cache, directive injection, session writes).

**Milestones:** 2.6.1 → 2.6.2

---
