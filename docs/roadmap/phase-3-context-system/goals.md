# Phase 3 — Goals

## Goal 3.1: Memory storage and retrieval

**Description:** Python memory service with tenant-scoped CRUD and vector similarity search.

**Acceptance criteria:**

- REST API matches documented memory endpoints subset
- Every query filters `org_id`; RLS + application-level checks
- pgvector index used; integration tests with real Postgres
- Deduplication/conflict hooks stubbed or minimal (full logic may span milestones)

**Validation:** Contract tests + cross-tenant integration tests

---

## Goal 3.2: Context assembly engine

**Description:** gRPC service implementing `ibex.context.v1.ContextAssemblyService`.

**Acceptance criteria:**

- `AssembleContext` returns packed context within `available_tokens`
- Deadline propagation; partial result on timeout documented
- Metrics per stage in `AssemblyMetrics`

**Validation:** gRPC integration tests; benchmark smoke vs PERFORMANCE.md budgets

---

## Goal 3.3: Proxy injection and async extraction

**Description:** Proxy invokes context assembly and injects memories as untrusted data; extraction runs in workers.

**Acceptance criteria:**

- Injection uses explicit delimiters; directive precedence documented
- Extraction never blocks LLM response
- High-risk memory quarantine path exists (write-time)

**Validation:** End-to-end test with mock provider + real context/memory in compose

---

## Deferred to Phase 4+

- Full conflict resolution UI
- Drift detection and fingerprinting workers
- Dashboard memory inspector
