# IBEX Harness — Testing Strategy

## 1) Purpose

IBEX Harness is a distributed, security-sensitive system with:

- strict multi-tenancy requirements,
- a latency-critical proxy path,
- complex ranking / scoring algorithms,
- async background processing,
- and multiple languages/services.

This testing strategy defines **what we test, how we test it, and what “done” means** from a correctness and reliability perspective.

**Core goal:** Prevent “it works on my machine” and “tests passed but production broke” by ensuring we test:

- real infrastructure behavior (DB/cache/queues),
- contract compatibility between services,
- failure modes and degraded modes,
- performance regressions in hot paths,
- tenant isolation invariants,
- security invariants.

---

## 2) Testing Principles (Non‑Negotiable)

### P1 — Test behavior, not implementation

Tests must verify externally observable behavior and invariants. Avoid tests that break under harmless refactoring.

### P2 — Integration tests use real dependencies

We test against real PostgreSQL (with pgvector), Redis, ClickHouse, MinIO where relevant.
Mocks are acceptable **only** for:

- external third-party APIs (LLM providers, GitHub, Slack),
- CPU-heavy ML models (in unit tests only),
- deterministic simulation of rare failures (time, network).

### P3 — Failures are first-class

For each feature, test both:

- the happy path, and
- explicit failure and timeout paths (auth down, Redis down, context assembly timeout, etc.)

### P4 — Multi-tenancy is tested explicitly

Tenant isolation is not “assumed.” It is verified by tests that attempt cross-tenant access in:

- PostgreSQL queries
- Redis key usage
- ClickHouse query filtering
- API endpoints

### P5 — Hot paths get performance tests

Proxy and context assembly changes require:

- a micro-benchmark (Go benchmark / Python perf test where applicable), or
- a load-test scenario in staging (k6).

### P6 — Tests must be deterministic enough to trust CI

Flaky tests erode trust and will be treated as failures.
If a test flakes twice in CI, it becomes a “stop the line” issue.

---

## 3) Test Pyramid and What Goes Where

### 3.1 Unit Tests (≈70%)

**Goal:** Validate business logic and algorithms in isolation.

Examples:

- memory scoring formula correctness
- token bucket math and edge cases
- session state machine transitions
- directive DAG rules
- validation logic
- error mapping to API responses

### 3.2 Integration Tests (≈20%)

**Goal:** Verify service logic against real infrastructure boundaries.

Examples:

- PostgreSQL RLS behavior with real transactions
- pgvector similarity queries with filters
- Redis rate limiting Lua scripts are atomic under concurrency
- ClickHouse inserts + queries match expected retention/partition behavior
- worker retry + idempotency correctness

### 3.3 E2E Tests (≈10%)

**Goal:** Verify the most critical user flows end-to-end.

Examples:

- dashboard login → list agents → view sessions → inspect context injection
- SDK initializes → creates session → makes proxied LLM call → memory written → memory retrievable
- directive promotion gated by regression suite

Only critical flows; E2E tests are the slowest and most fragile.

---

## 4) Tooling (by language / layer)

### Go (proxy, auth, CLI)

- Unit tests: `go test ./...`
- Assertions: standard library `testing` + `testify` allowed
- Race detection: `go test -race` required in CI for core services
- Benchmarks: `go test -bench . -benchmem` for hot paths
- Integration: `testcontainers-go` (Postgres, Redis)

### Python (FastAPI services, workers, algorithms)

- Unit tests: `pytest`
- Async tests: `pytest-asyncio`
- Property-based: `hypothesis`
- Integration: `testcontainers-python` (Postgres, Redis, ClickHouse, MinIO)
- Coverage: `coverage.py` (line + branch preferred)

### TypeScript (dashboard, SDK)

- Unit tests: `vitest`
- Component tests: React Testing Library
- E2E: `playwright` (preferred) or Cypress (acceptable)
- Type-level checks: `tsc --noEmit` is required CI gate

### Load / Performance

- `k6` for load testing critical endpoints (proxy, search, context)
- Optional: `vegeta` for pure HTTP load spikes

### Contract / Schema

- Protobuf linting + breaking change detection: `buf`
- OpenAPI validation: generated from FastAPI; snapshot testing of the spec

---

## 5) Test Environments

### 5.1 Local

- fastest developer loop
- can run unit tests and lightweight integration tests
- should use Docker for dependencies

### 5.2 CI (Pull Request)

- deterministic environment
- runs:
  - lint
  - typecheck
  - unit tests
  - integration tests (subset)
  - contract checks
  - security scanning
- should complete in ~10–20 minutes

### 5.3 Staging

- production-like environment
- runs:
  - full integration suite
  - E2E flows
  - load tests
  - chaos experiments (optional but recommended)

---

## 6) Service-by-Service Testing Requirements

### 6.1 Proxy Service (Go) — Critical Path

**Primary risks:**

- latency regressions
- streaming correctness
- goroutine leaks
- auth bypass
- rate limiting atomicity
- context injection correctness under timeouts

**Unit tests must cover:**

- request parsing and normalization
- header handling (agent_id/session_id required rules)
- circuit breaker state machine (closed → open → half-open)
- fallback behavior:
  - context assembly timeout ⇒ directive-only context
  - auth service down ⇒ cached claims path
  - Redis down ⇒ local conservative rate limiter
- streaming:
  - provider sends chunks faster than client reads (backpressure handling)
  - client disconnect mid-stream
  - provider disconnect mid-stream
  - correctness of accumulated final response vs streamed chunks

**Integration tests must cover (real Redis):**

- rate limit Lua script atomicity under concurrency:
  - N concurrent requests must never exceed allowance
- token validation cache correctness:
  - bloom filter negative should reject quickly
  - revocation propagation invalidates cache within target window

**Performance tests required:**

- benchmark for:
  - “auth cache hit” request path
  - “context assembly success” request path (with mocked upstream provider)
- regression thresholds (example):
  - p95 proxy overhead must not exceed 20ms in local perf benchmark
  - allocations/op in hot handler must not increase by >20% without justification

**Special test: goroutine leak detection**

- run `-race` in CI
- add a test that runs streaming handler repeatedly and checks:
  - goroutine count stabilizes (no growth)
  - context cancellations stop background tasks

---

### 6.2 Auth Service (Go) — Security Critical

**Primary risks:**

- incorrect permission enforcement
- token hashing bugs
- timing leaks (non-constant comparisons)
- revocation not propagating
- key rotation breaking tokens

**Unit tests must cover:**

- token generation constraints (length, prefix)
- hashing verification (Argon2id parameters, correct verify behavior)
- permission bitmap:
  - set/clear/test bits
  - reserved bits remain unused
  - permission checks are constant-time where appropriate
- JWT:
  - signed token verifies with public key
  - expired token rejected
  - key rotation:
    - current key signs
    - verifier accepts current + previous during grace period
    - old key rejected after sunset

**Integration tests must cover:**

- token stored in PostgreSQL can be validated end-to-end
- revocation:
  - revoke token, ensure proxies reject within propagation SLA
  - ensure revoked token cannot be used even if previously cached

**Security-specific tests:**

- ensure no endpoint returns token plaintext except on creation
- ensure logs never include token values (log scrubbing tests)

### 6.2.1 Proxy auth middleware (Go)

**Primary risks:**

- bypassing auth on protected routes
- fail-open when auth is unavailable
- bearer token leakage in logs
- cross-tenant scope on org-scoped paths

**Unit tests must cover:**

- bearer header parsing (missing, malformed, valid)
- middleware with mock `TokenValidator` (401/403/503/200)
- minimal stable error envelope JSON

**Integration tests must cover:**

- proxy + real auth gRPC + Postgres
- valid / invalid / revoked PAT
- org path mismatch → 403
- chat route requires `ProxyChatCompletion`
- auth stopped → 503 on protected routes

---

### 6.2.2 Proxy request normalization (Go)

**Primary risks:**

- parsing message content into logs
- accepting unbounded bodies before 1.2.3 limits
- bypassing auth and parsing unauthenticated bodies

**Unit tests must cover:**

- valid OpenAI-shaped JSON
- invalid/truncated JSON, non-array `messages`, non-object message elements
- httptest: auth + valid JSON → 501; auth + bad JSON → 400

**Integration tests must cover:**

- authenticated valid JSON → 501 `PROVIDER_NOT_CONFIGURED`
- authenticated malformed JSON → 400 `INVALID_JSON`

---

### 6.3 Memory Service (Python) — Data Integrity + Isolation

**Primary risks:**

- cross-tenant leakage
- deduplication false positives causing data loss
- pgvector query correctness with filters
- conflict resolution correctness
- PII / injection quarantine rules

**Unit tests must cover:**

- normalization + hashing rules:
  - whitespace normalization stable
  - identical semantic content with different whitespace hashes consistently
- dedup pipeline:
  - exact duplicate returns 409 (or “skip” depending endpoint)
  - near-duplicate triggers conflict detection workflow
- PII detection classification boundaries (at least regression tests on known samples)
- injection risk scoring gating:
  - score > threshold ⇒ status quarantined
  - quarantined memories never returned in default search

**Integration tests (real Postgres w/ RLS) must cover:**

- RLS is enforced:
  - attempt to query with wrong org_id context yields no rows
  - ensure connection pool resets org context per transaction
- vector search + filters correctness:
  - category filters applied correctly
  - tags filtering uses correct AND semantics
  - status filtering excludes deleted/archived as expected
- pgvector index usage:
  - ensure query plan uses ivfflat when appropriate (optional explain plan assertion)

**Cross-tenant test suite (mandatory):**

- create two orgs, two agents, write memory in org A
- attempt reads/search from org B must return:
  - 404 for direct lookup by ID (not “found but forbidden”)
  - empty set for searches
- validate Redis keys are namespaced:
  - ensure memory cache entry is stored under `{org_id}:...` key prefix

---

### 6.4 Context Assembly Engine (Python gRPC) — Algorithmic Correctness

**Primary risks:**

- ranking algorithm regressions
- budget overflow / context window exceeding provider limits
- unstable ordering causing nondeterministic behavior
- timeouts not honored (proxy must not stall)

**Unit tests must cover:**

- budget computation:
  - reserves correct response budget
  - enforces buffer
  - fails loudly if directive alone exceeds budget
- ranking formula:
  - weights sum to 1.0 (validate)
  - missing signals handled (null last_accessed_at)
  - tie-breaking deterministic (e.g., stable sort by memory_id)
- packing logic:
  - greedy algorithm behavior:
    - skip oversized memory and continue (or explicitly stop) — whichever spec chooses
  - ensures output token count <= budget
- injection ordering:
  - directive before memories
  - procedural before declarative before episodic
- fallback behavior:
  - cold retrieval timeout ⇒ hot only
  - hot retrieval failure ⇒ cold only
  - both fail ⇒ directive + history only

**Property-based tests (Hypothesis) must cover invariants:**

- **Invariant A:** assembled context token count never exceeds budget
- **Invariant B:** output ordering stable given same inputs
- **Invariant C:** increasing similarity of one memory never decreases its rank (monotonicity)
- **Invariant D:** if a memory is pinned, it is always included unless directive+history already consumes full budget

**Integration tests must cover:**

- gRPC interface compatibility with proxy client
- deadline enforcement:
  - server respects request deadline and returns partial context instead of hanging

---

### 6.5 Embedder Service (Python) — Determinism + Batching

**Primary risks:**

- nondeterministic embeddings across runs
- batching causing out-of-order output mismatch
- max length handling errors

**Unit tests must cover:**

- identical text yields identical embedding (within float tolerance)
- batching:
  - input list order preserved in output embeddings
  - mixed-length inputs handled correctly
- truncation/chunking rules for over-length inputs are explicit and tested

**Integration tests must cover:**

- service handles concurrency: many clients calling /embed in parallel
- queue/batching flush behavior respects time threshold and size threshold

---

### 6.6 Worker Service (Python Celery) — Idempotency + Retry Discipline

**Primary risks:**

- duplicate processing on retry causing duplicate memories/billing
- stuck tasks not visible
- DLQ not working
- partial failures leaving inconsistent state

**Unit tests must cover:**

- tasks are idempotent given idempotency key
- retry policies:
  - transient errors retry
  - validation errors do not retry
- failure handling:
  - task fails, goes to DLQ after max retries
  - DLQ metrics updated

**Integration tests must cover:**

- real Redis Streams / broker:
  - publish job, worker consumes, acknowledges
- worker crash simulation:
  - kill worker mid-task, ensure task re-queued and not double-applied

---

### 6.7 Dashboard (Next.js) — UX + Error Discipline

**Primary risks:**

- server/client boundary violations (App Router)
- missing loading/empty/error states
- token handling mistakes (XSS/CSRF)
- incorrect caching and stale data

**Unit/component tests must cover:**

- each “data view” renders:
  - loading state
  - empty state
  - error state
  - success state
- critical components: memory list, session replay, directive diff view

**E2E tests must cover (Playwright):**

- login flow (including refresh)
- view an agent
- view sessions
- inspect “why did agent do that?” trace view
- memory search in UI

---

## 7) Contract Testing

### 7.1 Protobuf (gRPC contracts)

- All `.proto` files:
  - linted by `buf lint`
  - breaking changes detected by `buf breaking` against main branch
- Generated code must be consistent:
  - CI runs “generate” and fails if there are uncommitted diffs in generated outputs

### 7.2 REST API (OpenAPI)

- FastAPI OpenAPI spec must be stable:
  - snapshot testing of the OpenAPI JSON for `/v1` (allow additive changes)
  - breaking changes require:
    - API version bump
    - explicit migration notes

---

## 8) Test Data Strategy

### 8.1 Isolation

- Tests must not depend on global mutable state
- Integration tests:
  - each test uses a unique org_id
  - each test runs in a DB transaction and rolls back, OR truncates tables safely

### 8.2 Fixtures

- Use explicit factories:

  ```text
  create_org()
  create_user()
  create_agent()
  create_memory()
  ```

- Fixtures must be deterministic and minimal

### 8.3 Golden datasets

For algorithm tests (ranking/drift), maintain a small canonical dataset:

- fixed inputs
- expected ordering / score ranges
- used for regression detection

---

## 9) Performance and Load Testing

### 9.1 Proxy load tests (k6)

Scenarios:

- steady RPS with mixed models
- burst traffic (spike tests)
- streaming heavy sessions
- degraded Redis mode

Pass/fail examples:

- p95 total overhead < 20ms (proxy-only)
- p99 overhead < 60ms
- error rate < 0.5% (excluding deliberate throttling tests)

### 9.2 Context assembly perf

- benchmark ranking with 100 candidates
- benchmark packing + formatting
- enforce p95 < 50ms on representative workload

### 9.3 Memory search load

- search with 1M+ memories in table (synthetic)
- ensure query latencies remain under targets
- verify pgvector index settings (lists/probes) under load

---

## 10) Failure Testing / Chaos (Staging)

Recommended weekly experiments:

- kill Redis primary
- introduce 500ms latency to embedder
- kill ClickHouse
- simulate Postgres failover
- drop network between proxy and context service briefly

Expected outcomes:

- system degrades gracefully (no total outage except unavoidable dependencies)
- security always fails closed (no accidental access granted)

---

## 11) Flaky Test Policy

A flaky test is a failure.

Procedure:

1. Mark test quarantined only if it blocks the entire pipeline and fix is non-trivial
2. Create an issue immediately
3. Fix within 48 hours
4. Remove quarantine

Never ignore flakes. Flakes create blind spots where real regressions slip through.

---

## 12) Coverage Policy

Coverage is a signal, not a goal — but we still enforce minimums:

- Go: ≥ 80% for critical packages (auth, ratelimit, streaming)
- Python: ≥ 85% for algorithms and security-related code
- TypeScript: ≥ 70% for core UI logic; E2E covers critical flows

More important than line coverage:

- branch coverage for decision-heavy code
- property-based tests for algorithmic invariants
- integration test breadth for multi-tenancy

---

## 13) “What Must Not Be Mocked” List (Hard Rule)

These components must be tested against real implementations in integration tests:

- PostgreSQL RLS behavior (never mock)
- Redis Lua rate limiting (never mock)
- pgvector similarity query execution (never mock)
- token revocation propagation behavior (never mock)
- session checkpoint storage and retrieval (never mock)

You may mock:

- upstream LLM provider responses (OpenAI/Anthropic)
- third-party webhooks (GitHub/Slack)
- optional external notifications (email/SMS)

---

## 14) CI Test Stages (Recommended)

### Stage A: Fast checks (every PR)

- lint + format
- typecheck
- unit tests

### Stage B: Integration subset (every PR)

- Postgres + Redis integration tests
- contract checks (buf + OpenAPI snapshot)

### Stage C: Full suite (merge to main / nightly)

- full integration tests including ClickHouse/MinIO
- E2E tests (Playwright)
- load tests (k6) (nightly or weekly)

---

## 15) Test Checklist Per Feature (Definition of Done)

Every feature PR must include:

- [ ] Unit tests for the core behavior
- [ ] Tests for failure modes
- [ ] Integration tests if DB/cache/queue behavior involved
- [ ] Tenant isolation tests if any data access involved
- [ ] Contract tests if interfaces changed
- [ ] Performance tests if hot path changed
- [ ] Documentation updates if behavior changed

---

This testing strategy is the enforcement mechanism that makes IBEX Harness safe to build quickly with AI assistance. If you skip tests, you are not moving faster — you are borrowing time from the future at compounding interest.
