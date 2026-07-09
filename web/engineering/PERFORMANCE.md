# IBEX Harness — Performance Engineering

## 1) Purpose

This document defines:

- performance budgets (latency/throughput) per subsystem,
- what “performance regression” means,
- how we benchmark and profile,
- and how we keep the proxy + context assembly fast over time.

Performance is a product requirement for IBEX Harness:

- the proxy sits on every inference call,
- context assembly runs on every inference call,
- any overhead compounds dramatically at scale.

---

## 2) Performance Budgets (Non‑Negotiable Targets)

### 2.1 Proxy service budgets (overhead only)

These numbers exclude upstream LLM provider latency.

- Proxy overhead:
  - p95 ≤ 20ms
  - p99 ≤ 60ms
- Auth validation:
  - cache hit p95 ≤ 2ms
  - cache miss p95 ≤ 20ms
- Rate limiting check:
  - p95 ≤ 5ms
- Context assembly RPC (end-to-end):
  - p95 ≤ 50ms
  - p99 ≤ 100ms
- Streaming:
  - per-chunk processing overhead should be near-zero (avoid per-chunk allocations)

### 2.2 Context assembly budgets

- Total assembly p95 ≤ 50ms, p99 ≤ 100ms
- Cold retrieval (vector search) budget: ≤ 30ms (typical)
- Ranking + packing budget: ≤ 15ms (100 candidates)
- Formatting budget: ≤ 5ms

### 2.3 Memory search budgets (Memory service)

- p95 ≤ 100ms (typical dataset sizes up to 10M vectors per tenant with pgvector IVFFlat)
- p99 ≤ 250ms

### 2.4 Memory write budgets

- p95 ≤ 200ms (including embedding in normal conditions)
- Degraded mode: if embedder down, accept write (queued) ≤ 50ms response time

### 2.5 Worker pipeline budgets (eventual)

- Memory extraction job: median ≤ 5s, p95 ≤ 30s (LLM-dependent)
- Conflict resolution job: median ≤ 2s, p95 ≤ 10s
- Fingerprint computation: median ≤ 1s, p95 ≤ 5s

---

## 3) “Critical Path” Definition and Rules

### 3.1 Critical path scope

Critical path is:
`Agent → Proxy → (Auth, Rate Limit, Context Assembly) → Provider → Proxy → Agent`

Everything not required for the response must be async:

- ClickHouse trace writes (buffer)
- memory extraction triggers (queue)
- billing events (buffer)
- notifications (queue)

### 3.2 Forbidden in critical path

- synchronous writes to ClickHouse
- synchronous writes to object storage
- long DB transactions
- unbounded retries
- per-request dynamic regex compilation
- per-chunk JSON re-parsing on streaming
- per-request allocation of large maps/slices without reuse

---

## 4) Benchmarking Strategy (CI + Local)

### 4.1 Go benchmarks (proxy/auth/ratelimit/streaming)

For any hot path change, add/update benchmarks.

Required benchmark categories:

- auth validation (hit/miss)
- rate limit check (single + concurrent)
- context injection formatting
- streaming handler overhead

Benchmark output to track:

- ns/op
- allocs/op
- bytes/op

**Regression policy:**

- >20% regression in ns/op or allocs/op is a merge blocker unless justified with a documented reason and compensating improvement.

### 4.2 Python perf tests (context/memory)

Python performance regressions often come from:

- accidental N+1 queries
- converting large objects repeatedly
- unnecessary JSON serialization
- slow loops instead of vectorized ops

Approach:

- add micro-bench tests for ranking/packing functions
- integration perf tests that measure DB query latency (pgvector search)
- guard with “performance budgets” where feasible (may be flaky; keep thresholds tolerant)

### 4.3 TypeScript performance budgets (dashboard)

We enforce:

- bundle budgets (per route) via build analysis (optional)
- page load times measured via Lighthouse CI (optional)
- avoid heavy chart libraries and large deps

---

## 5) Profiling Playbooks

### 5.1 Go proxy profiling

Tools:

- `pprof` CPU profile
- `pprof` heap profile
- execution tracing (`go tool trace`)
- `-race` for concurrency issues

Workflow:

1. Reproduce with load generator (k6 or local benchmark)
2. Capture profiles:
   - CPU for 30s under representative load
   - heap snapshot under steady load
3. Identify top allocators and hot functions
4. Optimize:
   - remove allocations (reuse buffers, builders)
   - reduce JSON parsing overhead (streaming decode)
   - avoid interface{} conversions in hot path
5. Re-run benchmark to verify improvement

### 5.2 Python service profiling

Tools:

- `py-spy` for sampling CPU profiling in production-like runs
- `cProfile` for focused profiling
- SQLAlchemy logging for slow query detection
- Postgres `EXPLAIN (ANALYZE, BUFFERS)` for vector queries

Workflow:

1. Identify whether the bottleneck is:
   - CPU (Python loops)
   - DB (slow query, missing index, poor filter)
   - network (redis, embedder)
2. For DB bottlenecks:
   - capture query and run EXPLAIN ANALYZE
   - verify it uses intended index
3. For CPU bottlenecks:
   - vectorize operations or reduce data processed
   - cache computed values
4. Verify improvements with perf tests

### 5.3 ClickHouse profiling

- use system tables: `system.query_log`
- check merges backlog and disk usage
- optimize ORDER BY and partitioning if queries scan too much data

---

## 6) Performance Regression Gates

### 6.1 CI regression checks (recommended)

- Go benchmarks run on main nightly (not every PR), with historical tracking
- Compare current benchmark result to baseline
- Alert on regression, open automated issue

### 6.2 Staging load tests

Weekly or before major releases:

- k6 scenario for proxy at 10x expected load
- check p95/p99 overhead and error rate
- check degraded mode behaviors (simulate Redis down, context timeout)

---

## 7) Data Access Performance Rules (DB and Cache)

### 7.1 PostgreSQL query rules

- no unbounded queries (always limit/paginate)
- avoid OFFSET pagination for large tables
- ensure indexes exist for every frequent filter pattern
- prefer `EXPLAIN` verification for any new vector query

### 7.2 pgvector tuning (initial guidance)

- IVFFlat lists:
  - starting point: `lists ≈ sqrt(N)` for N vectors per partition/tenant
- probes:
  - tune via experiments; trade recall vs latency
- plan migration to Qdrant when:
  - >50M vectors per tenant with high QPS
  - or pgvector query latency degrades beyond SLOs

### 7.3 Redis usage rules

- enforce TTL for cache keys
- avoid large values (store IDs; fetch details from DB if huge)
- avoid high-frequency writes in hot path unless necessary
- use Lua scripts for atomic operations that must be consistent across instances (rate limiting)

---

## 8) Observability for Performance (what to instrument)

To debug latency, you must measure:

- proxy stage timings
- context stage timings
- DB query timings
- Redis latencies
- provider latencies
- fallback occurrences

Without stage breakdown metrics, latency regressions become guesswork.

---

## 9) Checklist: Performance “Done” for Critical Changes

Any change touching proxy/context must include:

- [ ] benchmark updated or added (Go)
- [ ] stage timings validated (metrics)
- [ ] no new allocations in streaming hot loop (verified by benchmark allocs/op)
- [ ] timeouts remain in place
- [ ] fallbacks preserved (don’t trade correctness for speed)
- [ ] load test plan updated if behavior changes significantly

---

Performance is part of correctness. A correct system that is too slow is not correct for IBEX Harness.
