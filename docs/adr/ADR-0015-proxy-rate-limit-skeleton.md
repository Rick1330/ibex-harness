# ADR-0015: Proxy rate limit skeleton (Phase 1)

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** IBEX Harness team

## Context

Phase 2 will call real LLM providers; without rate limiting, runaway tests can exhaust credits. Phase 4 adds hierarchical Redis Lua limits. Milestone 1.2.4 introduces a minimal org-level limiter in the proxy pipeline **after auth** and before handlers, without blocking traffic when Redis is unavailable.

## Decision

### 1) Package layout

- **`packages/ratelimit`** — `Limiter` interface, `RedisSlider` implementation (Redis INCR + EXPIRE), `ParseRedisURL`
- **`services/proxy/internal/http/ratelimit_middleware.go`** — HTTP middleware only; no direct Redis calls in proxy
- Config remains in `services/proxy/internal/config` until M1.4.2 (`packages/config`)

### 2) Algorithm (Phase 1)

- Org-level calendar-minute window: key `ratelimit:{org_id}:rpm:{unix_minute}` per [15-redis-patterns.mdc](../../.cursor/rules/15-redis-patterns.mdc)
- On first increment in a window: `EXPIRE` **90s** (clock skew buffer)
- **Not atomic** — acceptable soft limit until Phase 4 Lua scripts
- `agentID` parameter accepted on `Check` but **ignored** in Phase 1 (org-level only)
- `BurstSize` reserved for Phase 4; Phase 1 enforces `requests_per_minute` only

### 3) Fail-open vs fail-closed

| Control | Redis failure behavior |
| --- | --- |
| Auth | Fail closed → **503** `SERVICE_DEGRADED` |
| Rate limit | Fail **open** → allow request + warn log |

Rationale: rate limiting is cost/quality control, not a security boundary.

### 4) HTTP mapping

| Condition | HTTP | `code` |
| --- | --- | --- |
| Over org RPM | 429 | `RATE_LIMITED` |

Response headers on limited or allowed requests:

- `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix seconds)
- `Retry-After` (seconds, min 1) on **429** only

Stable envelope via `services/proxy/internal/errors` (not `packages/apierror` until M1.4.2).

### 5) Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `IBEX_RATE_LIMIT_DEFAULT_RPM` | `60` | Org default |
| `IBEX_RATE_LIMIT_ORG_OVERRIDES` | (empty) | `uuid=rpm,uuid2=rpm2` |

No DB-backed limits in Phase 1.

### 6) Middleware order

Amends [ADR-0013](ADR-0013-proxy-input-validation-and-error-envelope.md) §8:

```text
POST /v1/chat/completions:
  bodyLimit → contentType → auth → rateLimit → handler

GET /v1/internal/auth-probe:
  auth → rateLimit → handler

GET /v1/orgs/{org_id}/auth-probe:
  pathOrgUUID → auth → rateLimit → handler
```

### 7) Deferred

- Agent-level and hierarchical limits (Phase 4 Lua)
- Prometheus rate-limit metrics (M1.3.2)
- `packages/apierror` code registry (M1.4.2)
- End-to-end security matrix (M1.5.1)

## Consequences

### Positive

- Cost protection before Phase 2 provider calls
- Interface stable for Phase 4 replacement of `RedisSlider` internals
- Per-org isolation via Redis key naming

### Negative

- Non-atomic INCR may allow slight overshoot under concurrency
- Auth context `org_id` must be a valid UUID string for rate limit middleware

## References

- [Milestone 1.2.4](../roadmap/phase-1-core-platform/milestones/1.2.4-proxy-rate-limit-skeleton.md)
- [ADR-0013](ADR-0013-proxy-input-validation-and-error-envelope.md)
- [DATABASE_SCHEMA.md](../DATABASE_SCHEMA.md) — Redis rate limit keys
