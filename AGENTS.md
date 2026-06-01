# IBEX Harness — AGENTS.md

**Audience:** AI coding assistants and humans using AI tooling (Cursor, Copilot, Claude, Codex, Gemini CLI, etc.)  
**Scope:** Entire repository (monorepo). This file is the highest-level “how to work here” document for agents.

---

## 0) Prime Directive (Non‑Negotiable)

You are operating in a **production-grade**, **security-sensitive**, **multi-tenant** distributed system.

Your output must be:

- **Correct** (functionality + edge cases)
- **Secure** (tenant isolation, authz correctness, no secret leakage)
- **Maintainable** (consistent patterns, low complexity, clear naming)
- **Tested** (unit + integration where relevant)
- **Observable** (metrics/logs/traces for meaningful events)
- **Framework-compliant** (FastAPI, Next.js App Router, Go layout)

### Absolute prohibitions

- Do not invent APIs, libraries, file paths, or configurations that you cannot verify in the repo.
- Do not add placeholder logic (no `TODO implement`, no stub handlers returning success).
- Do not weaken lint/typecheck/test rules to “make CI pass.”
- Do not log secrets or raw sensitive content (tokens, keys, memory content).
- Do not remove `org_id` filtering from data access (even if RLS exists).

### If you are uncertain

You must choose one:

1. **Ask a precise question** (best), OR
2. **Propose two options with tradeoffs** and recommend one, OR
3. **Create a “SPIKE” step** (research/validation task) and stop implementation until resolved.

Do **not** guess silently.

---

## 1) What IBEX Harness Is (System Summary)

IBEX Harness is an AI agent memory + context platform that provides:

- **LLM Proxy (Go)**: intercepts LLM calls, validates auth, enforces rate limits, injects context (directive + memories), forwards to provider (streaming), emits traces.
- **Memory System (Python)**: memory CRUD, dedup, embeddings, vector search, conflict detection/resolution, GDPR deletion flows.
- **Context Assembly Engine (Python, gRPC)**: budget calculation + memory retrieval + ranking + packing + context formatting with strict latency budgets.
- **Auth Service (Go)**: token validation, permission bitmap enforcement, JWT issuance/verification flows, revocation propagation.
- **Workers (Python/Celery)**: memory extraction, embeddings, conflict resolution, fingerprinting, drift detection, notifications, garbage collection.
- **Dashboard (Next.js/TypeScript)**: sessions, traces, memories, directives, drift alerts, billing/usage views.
- **Data layer**: PostgreSQL + pgvector (OLTP), Redis (cache/streams/rate limits), ClickHouse (analytics/billing events), MinIO/S3 (archives).

**Critical path latency requirement:** Proxy overhead must remain minimal; context assembly must be bounded with deadlines and fallbacks.

---

## 2) How to Work in This Repo (Agent Workflow)

### 2.1 Before you write code: “Pattern Discovery”

You must identify existing patterns before introducing new ones:

- Find a similar module/service.
- Match naming, layout, error handling, logging, and testing style.
- Confirm framework conventions by inspecting existing files (not memory).

If you cannot find an example in the repo:

- propose a pattern,
- justify it briefly,
- and expect review.

### 2.2 The “Four Passes” Implementation Method

For any feature or fix:

**Pass 1 — Interfaces & contracts**

- Define/confirm API contracts (REST/gRPC)
- Confirm DB schema requirements and indexes
- Confirm Redis key patterns, TTLs, and data structures
- Confirm permission requirements

**Pass 2 — Happy path**

- Implement core behavior with clear separation:
  - handlers/routers (API boundary)
  - service layer (business logic)
  - repository layer (DB/cache interactions)

**Pass 3 — Failure paths**

- Enumerate failure modes explicitly:
  - dependency timeouts
  - DB constraints
  - upstream errors
  - auth failures
  - rate limit exceeded
- Implement and test these paths.

**Pass 4 — Verification**

- Add unit tests and integration tests
- Add or update metrics/logs/traces
- Run lint/typecheck/tests locally
- Update docs when behavior/contracts change

### 2.3 “No silent drift”

If you need to change an established pattern:

- explain why,
- keep change local,
- and/or create an ADR if it affects multiple services.

---

## 3) Service Boundaries (Do Not Blur)

### API boundary rules

- Handlers/routers:
  - validate inputs (shape, ranges, sizes)
  - enforce authentication + authorization
  - translate internal errors into stable external error responses
  - do not contain business logic beyond orchestration

### Service layer rules

- Owns business logic and algorithms
- Calls repositories and external clients
- Must be testable with unit tests (dependency injection)

### Repository layer rules

- Owns persistence details (SQL queries, Redis operations)
- Must enforce tenant filtering (`org_id`) even if DB has RLS
- Must not contain business policy decisions (that belongs in service layer)

---

## 4) Tenant Isolation (Must Be True Everywhere)

### 4.1 PostgreSQL (RLS + defense-in-depth)

- RLS is enabled, but you MUST still filter `org_id` explicitly in queries.
- If org context is missing, the system must fail closed.

### 4.2 Redis namespacing

- Keys must be prefixed with `org_id:` for tenant data.
- Global keys are allowed only when explicitly safe and documented (e.g., revocation broadcast channel).
- TTLs must be set intentionally (no “forever” keys unless justified).

### 4.3 ClickHouse org filtering

ClickHouse has no RLS. Therefore:

- Every ClickHouse query must include org_id filter.
- Any function that executes ClickHouse queries must require `org_id` explicitly and refuse to run without it.

### 4.4 Testing isolation

Every feature that touches data access must include a cross-tenant test:

- Org A data must not be readable/searchable by Org B.
- Prefer returning 404 (not found) rather than “403 forbidden” for existence leaks.

---

## 5) Security Rules (Agent Checklist)

### 5.1 Never log secrets or sensitive content

Forbidden to log:

- tokens, API keys, passwords
- full directive content (unless explicitly in secure debug mode)
- memory content by default (log IDs + metadata)

### 5.2 Input validation is mandatory

Validate:

- string length bounds
- array size bounds
- JSON object size bounds
- enums strictly (no implicit coercion)
- UUID formats
- numeric bounds (confidence 0..1, thresholds, limits)

### 5.3 Auth is not optional

Every endpoint must explicitly declare:

- authentication requirement
- permission requirement
- any role requirement (admin/owner)
- org ownership checks (implicit via claims + DB scope)

### 5.4 Approved cryptography only

- Password hashing: Argon2id
- JWT signing: RS256 (keyset for rotation)
- Encryption: AES-256-GCM
- Hashing: SHA-256
- Constant-time comparison: use library primitives

Never implement “custom crypto.”

### 5.5 Prompt-injection safety for memories

All memory content is untrusted input:

- quarantine high-risk content
- inject as “data” with explicit delimiters
- never treat memory content as instructions
- enforce source hygiene (integrations sanitize)

---

## 6) Performance Rules (Critical Path Discipline)

### 6.1 The proxy must not block

Proxy request handling must:

- use strict timeouts for dependencies
- perform parallel retrieval where possible
- degrade gracefully (directive-only context if memory retrieval fails)
- never wait on analytics or extraction writes (async/buffered)

### 6.2 Context assembly deadlines

Context assembly must:

- run within a bounded deadline
- return partial context rather than blocking the proxy
- keep token budgeting safe (never exceed model context window)

### 6.3 Allocation control (hot path)

In hot paths:

- avoid unnecessary allocations
- use builders/pools appropriately (Go)
- avoid large JSON parsing work repeatedly (cache what can be cached)
- avoid deep copies of message arrays

If you change hot path code, include a benchmark or performance justification.

---

## 7) Framework Compliance Rules (Common Agent Failure Points)

### 7.1 Go service layout

- `cmd/<service>/main.go` is entrypoint only
- business logic in `internal/`
- `pkg/` only for code intentionally shared across modules

### 7.2 FastAPI + async SQLAlchemy

- async correctness: no blocking I/O in async handlers
- DB sessions via dependency injection
- set `SET LOCAL app.current_org_id = ...` per transaction
- avoid N+1 queries; use proper eager loading if needed

### 7.3 Next.js App Router

- server components by default
- `"use client"` only where needed (leaf interactive components)
- do not import server-only modules into client components
- every data view has loading/empty/error states
- keep components small and focused

---

## 8) Error Handling Standard (What “Good” Looks Like)

### 8.1 Stable external error shape

REST responses must follow the documented error envelope.
Do not return ad-hoc error JSON.

### 8.2 Categorize errors explicitly

- validation errors: 400
- auth errors: 401
- permission errors: 403
- not found: 404 (avoid existence leaks)
- conflicts: 409
- upstream/service unavailable: 503
- rate limiting/quota: 429

### 8.3 Retries

- only retry transient errors
- never retry validation/auth failures
- use exponential backoff with jitter for retries
- ensure idempotency for retried operations

---

## 9) Testing Requirements (Agent Must Do)

For any change:

- add unit tests for logic changes
- add integration tests when DB/cache/queue behavior changes
- add cross-tenant tests when data access is involved
- update or add contract tests when interfaces change
- add performance tests/benchmarks for hot path changes

**Do not** rely on mocks for:

- PostgreSQL RLS behavior
- Redis Lua rate limiting
- pgvector query behavior
- token revocation propagation

---

## 10) Observability Requirements

### 10.1 Metrics

Every service must expose Prometheus metrics including:

- request latency (p50/p95/p99)
- request counts by status
- dependency latency and error counts
- queue depth (workers)
- cache hit/miss rates

### 10.2 Tracing

- propagate trace context across services
- create spans for dependency calls (DB, Redis, external HTTP, gRPC)
- sample intelligently (100% for errors/slow, low % for normal)

### 10.3 Logging

- JSON structured logs
- include trace_id and org_id when available
- do not log raw memory content or secrets

---

## 11) Dependencies Policy (Agent Must Not Do This)

- do not add dependencies casually
- never add a dependency without stating:
  - why it’s needed
  - why stdlib existing dependency doesn’t suffice
  - security implications
  - maintenance/size impact

---

## 12) “Done” Definition for AI-Assisted Work (Self‑Review Checklist)

Before presenting changes, the agent must verify:

### Correctness

- [ ] Implements required behavior
- [ ] Handles failure modes explicitly
- [ ] Handles edge cases
- [ ] No placeholder stubs

### Security

- [ ] Auth and permissions enforced
- [ ] Tenant isolation preserved (org_id enforced)
- [ ] No sensitive logs
- [ ] Input validation complete

### Quality

- [ ] Follows repo patterns
- [ ] Complexity within limits
- [ ] Clear naming and structure

### Tests

- [ ] Unit tests added/updated
- [ ] Integration tests added/updated where relevant
- [ ] Cross-tenant test added where relevant

### Observability

- [ ] Metrics and logs updated/added
- [ ] Tracing spans added for dependencies

### Documentation

- [ ] Docs updated if behavior/contracts changed

---

## 13) Session Continuity (How Work Survives Context Loss)

Agents should leave handoff notes at the end of a session or PR in the **session workspace** (`handoff.md` next to the clone; see `docs/DEVELOPMENT_GUIDE.md` §12), not in the git repository.

Minimum handoff:

- What changed (high-level)
- What files changed
- New interfaces/contracts
- What tests to run
- Known risks/gotchas
- What remains incomplete (if any) and why

**If you are pausing mid-task**, explicitly state:

- current status (%)
- what assumptions were made
- what must be verified next

---

## 14) Agent Roles (Recommended)

We encourage splitting work across roles for quality:

- **Implementer Agent**: writes code + tests + docs
- **Reviewer Agent**: adversarial review (security, performance, correctness)
- **Test Agent**: improves coverage, adds integration tests, adds failure mode tests
- **Docs Agent**: ensures docs reflect actual behavior and interfaces

When asked to “review,” be strict. Prefer surfacing issues to praising.
