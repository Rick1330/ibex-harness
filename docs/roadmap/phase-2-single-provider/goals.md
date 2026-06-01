# Phase 2 — Goals

## Goal 2.1: Provider client and forwarding

**Description:** Implement an OpenAI-compatible HTTP client in the proxy with strict timeouts, connection pooling, and structured error mapping.

**Acceptance criteria:**

- `POST /v1/chat/completions` (or documented proxy path) forwards to configured provider base URL
- Non-streaming and streaming modes supported
- Provider errors mapped to documented error envelope
- No provider API keys in logs or metrics labels

**Related milestones:** (to be added) `2.1.1-provider-client`, `2.1.2-streaming-forward`

**Validation:** Integration test with httptest mock provider; manual curl against OpenAI sandbox key

---

## Goal 2.2: Authenticated critical path

**Description:** Every LLM proxy request validates token via auth service (or cache) before provider call.

**Acceptance criteria:**

- Missing/invalid token → 401; insufficient permission → 403
- Valid token attaches `org_id` to request context for downstream use
- Cross-tenant test: Org A token cannot influence Org B resources

**Related milestones:** Builds on Phase 1 Goal 1.2; may add `2.2.1-auth-cache-bloom` (optional)

**Validation:** Integration tests with two orgs in Postgres

---

## Goal 2.3: Async observability on hot path

**Description:** Emit traces and billing-related events without blocking response bytes to the client.

**Acceptance criteria:**

- Proxy returns first byte within budget when provider is fast
- Trace write failures do not fail the LLM response
- Metrics include stage breakdown (auth, normalize, provider TTFB)

**Related milestones:** `2.3.1-trace-async`, may extend Phase 1 observability

**Validation:** Load test smoke; verify ClickHouse or log sink receives events post-request

---

## Optional / deferred in Phase 2

- Multi-provider routing (Phase 4)
- Context/memory injection (Phase 3)
- Full Redis hierarchical rate limits (Phase 4)
