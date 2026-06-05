# Phase 1 — Comprehensive Gap Analysis
<!-- Last reviewed: 2026-06-05 | Reviewed against: CURRENT_STATE.md, ARCHITECTURE.md, DATABASE_SCHEMA.md, goals.md, all milestone files -->

## Audit Summary

| Category | Count |
|---|---|
| Security gaps (unacceptable before Phase 2) | 3 |
| Missing milestones (entirely absent from plan) | 9 |
| Under-specified planned milestones | 2 |
| Infrastructure / DX gaps | 4 |
| Quality gaps in delivered milestones | 3 |

---

## Security Gaps — Must Fix Before Phase 2

### S-1: `X-IBEX-Agent-ID` is never validated against the database

**Severity:** Critical  
**Where introduced:** M1.2.3 — proxy input validation  
**What happens today:** The proxy reads `X-IBEX-Agent-ID` from the request header, extracts the UUID, and attaches it to the request context. Nothing checks whether that UUID refers to a real agent or whether that agent belongs to the authenticated org.

**Attack vector:** Org A holds a valid token. Org B has agent `7f3a...`. Org A sends `X-IBEX-Agent-ID: 7f3a...`. The proxy attaches that context, and any downstream service that queries by agent_id without a org_id join will operate on Org B's agent. This is a cross-tenant confusion attack.

**Root cause:** There is no `ibex_core.agents` table yet. The milestone to create it (1.1.7) is absent from the plan entirely.

**Fix:** M1.1.7 (users + agents migrations) + M1.2.5 (agent identity verification middleware).

---

### S-2: No `ibex_core.users` table — tokens.user_id has no FK enforcement

**Severity:** High  
**Where documented:** DATABASE_SCHEMA.md note: _"tokens.user_id, tokens.agent_id, and tokens.revoked_by are nullable without foreign keys until users/agents tables exist."_

**What happens today:** `tokens.user_id` is a UUID column with no FK constraint. Any UUID can be stored as `user_id`. Token revocation by user cannot be reliably scoped. The `revoked_by` column has no referential integrity.

**Fix:** M1.1.7 introduces the `users` migration and adds the FK constraints deferred in M1.1.1.

---

### S-3: No cross-tenant integration test through the proxy

**Severity:** High  
**What exists:** Goal 1.1 has a cross-tenant RLS test at the DB level (SQL session isolation). There is no test that validates multi-tenant isolation end-to-end through the proxy's HTTP + auth + context path.

**What is missing:** A test that asserts:
- Token from Org A + resource UUID from Org B → 403
- Revoked token → 401 within the 50 ms gRPC budget
- Token with insufficient permission bitmap → 403

Without this test, a regression in any middleware ordering or context propagation can silently break tenant isolation.

**Fix:** M1.5.1 — Phase 1 security integration test suite.

---

## Missing Milestones — Not In Plan At All

### M1.1.7 — Core domain schema: `users` and `agents` migrations

The `tokens` table was migrated in M1.1.1 with nullable FKs to `users` and `agents`. Those tables were never added to the plan. The `agents` table is required before the proxy can verify agent identity (S-1). The `users` table is required for complete token revocation and audit trail integrity (S-2).

**Added to:** Goal 1.1 — Persistence and auth data plane  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.1.7-users-and-agents-schema.md`

---

### M1.2.5 — Agent identity verification in proxy middleware

Once `agents` exists (M1.1.7), the proxy must verify that `X-IBEX-Agent-ID` refers to a real, active agent belonging to the authenticated org. This is a single additional check in the middleware chain: after auth validation, before rate limiting.

**Added to:** Goal 1.2 — Proxy platform integration  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.2.5-proxy-agent-identity-verification.md`

---

### M1.2.6 — Request ID generation and correlation middleware

ARCHITECTURE.md mandates `trace_id` and `request_id` in every log line. M1.3.1 mentions "propagate `trace_id` in logs" as a single bullet but does not define the middleware that generates the ID. Without a request ID, log lines from a multi-step request (proxy → auth gRPC → response) cannot be correlated.

**Added to:** Goal 1.2 — Proxy platform integration  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.2.6-request-id-correlation-middleware.md`

---

### M1.2.7 — Graceful shutdown and connection draining for Go services

Both `services/auth` and `services/proxy` have no SIGTERM handling. The proxy is designed for 10,000+ simultaneous connections. Without graceful shutdown, Kubernetes rolling restarts drop in-flight requests. This is a P0 production readiness requirement and must exist before Phase 2 adds real LLM forwarding.

**Added to:** Goal 1.2 — Proxy platform integration  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.2.7-graceful-shutdown.md`

---

### M1.3.2 — Prometheus metric catalog and client migration

M1.3.1 conflates OTel initialization with Prometheus migration into a single 64-line milestone. The Prometheus work is substantial on its own: replace the custom mutex-based metrics with `prometheus/client_golang`, define canonical metric names from ARCHITECTURE.md, enforce no high-cardinality labels, and validate the `/metrics` exposition format in CI.

**Added to:** Goal 1.3 — Observability baseline  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.3.2-prometheus-metric-catalog.md`

---

### M1.3.3 — Shared structured logger package (`packages/logger`)

ARCHITECTURE.md defines a mandatory JSON log schema with `service`, `trace_id`, `org_id`, `request_id` fields. Two Go services rolling their own logging will diverge. A shared `packages/logger` wrapping `log/slog` with compile-time field enforcement is necessary before both services have observability work done on them.

**Added to:** Goal 1.3 — Observability baseline  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.3.3-shared-logger-package.md`

---

### M1.4.1 — Developer experience baseline: seed data, `.env.example`, local smoke test

CURRENT_STATE.md explicitly lists "`make db-seed` (dev seed data — future milestone)" as not existing. README notes `.env.example` files "to be created." Without seed data, a developer cannot obtain a working PAT to test the proxy. Without `.env.example`, onboarding requires reading multiple docs to discover required env vars.

**New goal:** Goal 1.4 — Developer Experience Baseline  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.4.1-developer-experience-baseline.md`

---

### M1.4.2 — Shared infrastructure packages: `packages/config` and `packages/apierror`

Both services scatter `os.Getenv()` calls with no schema validation at startup. A service that silently starts with a missing `POSTGRES_DSN` will fail at runtime with an opaque error, not at boot with a clear message. Similarly, the error codes introduced in M1.2.3 are string literals duplicated across packages — a `packages/apierror` canonical registry prevents drift.

**New goal:** Goal 1.4 — Developer Experience Baseline  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.4.2-shared-config-and-error-packages.md`

---

### M1.5.1 — Phase 1 security integration test suite (cross-tenant + auth boundary)

The security model is only as strong as the tests that verify it end-to-end. This milestone consolidates all cross-boundary integration tests: cross-tenant access via proxy, permission bitmap enforcement, revocation latency, rate limit headers. It is the explicit gate for Phase 1 completion.

**New goal:** Goal 1.5 — Phase 1 Security Gate  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.5.1-security-integration-test-suite.md`

---

## Under-Specified Planned Milestones

### M1.2.4 — Rate limit skeleton: quality gaps

| Gap | Impact |
|---|---|
| Non-atomic INCR race not covered by any concurrent test | Rate limit is effectively untested under load |
| Config schema undefined (file format, location, hot-reload) | Developers cannot configure without reading source |
| Redis key format `{org_id}:ratelimit:minute:{unix_minute}` contradicts DATABASE_SCHEMA.md Redis patterns which use `ratelimit:{org_id}:minute` | Key space inconsistency, cache debugging nightmare |
| No ADR for rate limit algorithm choice (INCR window vs token bucket vs sliding log) | Phase 4 will have to re-litigate the decision |
| Retry-After value is set but not verified as mathematically accurate in tests | Clients receive wrong backoff instructions |
| Fail-open behaviour is stated but untested (no integration test with Redis down) | Confidence in the fail-open path is zero |

See rewritten milestone: `1.2.4-proxy-rate-limit-skeleton.md`

---

### M1.3.1 — Observability baseline: quality gaps

| Gap | Impact |
|---|---|
| 64 lines covering OTel init, span middleware, Prometheus migration, and log propagation in one PR | Unacceptably large scope; unreviable; each concern deserves its own diff |
| No list of required Prometheus metric names | Reviewers cannot determine completeness |
| No OTel resource attribute specification (`service.name`, `service.version`, `service.instance.id`) | Traces in Jaeger/Tempo will be unlabelled |
| No structured log field schema (what fields are mandatory, what types, what are forbidden) | Log analysis is unreliable |
| "PERFORMANCE.md metrics plan noted for Phase 2" is not actionable | Performance regression detection deferred indefinitely |

M1.3.1 is split into M1.3.1 (OTel providers), M1.3.2 (Prometheus catalog), M1.3.3 (shared logger).

---

## Infrastructure / DX Gaps

| ID | Gap | Status |
|---|---|---|
| DX-1 | `make db-seed` does not exist | Addressed in M1.4.1 |
| DX-2 | `.env.example` files absent in service directories | Addressed in M1.4.1 |
| DX-3 | No health check response schema defined | Addressed in M1.4.3 (see below) |
| DX-4 | No Phase 1 exit criteria document | Addressed by adding M1.5.1 as explicit gate |

---

### M1.4.3 — Health check contract

Both services expose `/health` (liveness) and `/ready` (readiness) but with no defined response schema, no specification of what each probe checks, and no contract for Kubernetes probe configuration. This is a separate, small milestone that must precede any Kubernetes deployment work.

**New goal:** Goal 1.4 — Developer Experience Baseline  
**File:** `docs/roadmap/phase-1-core-platform/milestones/1.4.3-health-check-contract.md`

---

## Quality Issues in Delivered Milestones

### M1.1.1 (Delivered)
The migration for `tokens.user_id` and `tokens.agent_id` was deliberately made nullable without FKs. The plan to add those FKs never made it into a milestone. M1.1.7 closes this.

### M1.2.3 (Delivered)
`X-IBEX-Agent-ID` extraction was added. The validation that the agent belongs to the org was not added. M1.2.5 closes this.

### M1.2.1 (Delivered)
The gRPC connection to auth has no keepalive parameters, no retry interceptor, and no connection health checking documented. M1.2.7 addresses the lifecycle piece; gRPC connection hardening is added to M1.3.1's scope (OTel interceptors and keepalive).

---

## Revised Phase 1 Milestone Map

```text
Goal 1.0 — Test Infrastructure
  1.0.1  Go integration test infra              ✅ DONE

Goal 1.1 — Persistence and Auth Data Plane
  1.1.1  Postgres migration system              ✅ DONE
  1.1.2  Auth protobuf and codegen              ✅ DONE
  1.1.3  Auth ValidateToken gRPC                ✅ DONE
  1.1.4  Token creation and management API      ✅ DONE
  1.1.5  Permission bitmap contract             ✅ DONE
  1.1.6  Argon2id parameters and crypto policy  ✅ DONE
  1.1.7  Users and agents schema migration      🆕 MISSING — CRITICAL

Goal 1.2 — Proxy Platform Integration
  1.2.1  Proxy auth client                      ✅ DONE
  1.2.2  Proxy request normalization            ✅ DONE
  1.2.3  Proxy input validation + error envelope ✅ DONE
  1.2.4  Proxy rate limit skeleton              🔄 PLANNED (rewritten)
  1.2.5  Agent identity verification middleware  🆕 MISSING — SECURITY
  1.2.6  Request ID + correlation middleware     🆕 MISSING
  1.2.7  Graceful shutdown + connection draining 🆕 MISSING

Goal 1.3 — Observability Baseline
  1.3.1  OTel tracer/meter provider init         🔄 PLANNED (rewritten, scope reduced)
  1.3.2  Prometheus metric catalog               🆕 SPLIT FROM 1.3.1
  1.3.3  Shared structured logger package        🆕 SPLIT FROM 1.3.1 + NEW

Goal 1.4 — Developer Experience Baseline       🆕 NEW GOAL
  1.4.1  Seed data, .env.example, local smoke    🆕 MISSING — DX
  1.4.2  packages/config + packages/apierror     🆕 MISSING — INFRA
  1.4.3  Health check contract                   🆕 MISSING — OPS

Goal 1.5 — Phase 1 Security Gate               🆕 NEW GOAL
  1.5.1  Cross-tenant security integration suite 🆕 MISSING — GATE
```

**Recommended execution order after M1.2.3:**
`1.1.7 → 1.2.4 → 1.2.5 → 1.2.6 → 1.2.7 → 1.3.3 → 1.3.1 → 1.3.2 → 1.4.1 → 1.4.2 → 1.4.3 → 1.5.1`

`1.1.7` must precede `1.2.5`. `1.3.3` (shared logger) must precede `1.3.1` and `1.3.2` so both observability milestones adopt the shared logger from the start. `1.5.1` is the explicit Phase 1 completion gate.
