# Phase 4 — Goals

## Goal 4.1: Provider adapter layer

**Description:** Pluggable adapters behind a stable internal interface in `services/proxy`.

**Acceptance criteria:**

- Add second provider without duplicating streaming/auth logic
- Provider-specific quirks isolated in adapter package
- Config-driven provider registry per org

**Validation:** Integration tests per adapter; contract tests for normalized internal request type

---

## Goal 4.2: Routing and failover

**Description:** Route models to providers with fallback when primary unavailable.

**Acceptance criteria:**

- Routing rules stored in Postgres or Redis with cache
- Failover respects circuit breaker state
- Documented behavior when all providers down (503)

**Validation:** Chaos test: primary provider returns 503 → fallback succeeds

---

## Goal 4.3: Hierarchical rate limiting

**Description:** Redis Lua scripts enforce limits at agent, org, and global levels.

**Acceptance criteria:**

- Atomic increment/check in Lua
- 429 responses with stable error body
- Integration test proves limit enforcement (no mocks for Lua atomicity)

**Validation:** TESTING_STRATEGY.md Redis tests with real Redis

---

## Deferred

- Marketplace tokens and federation (architecture describes; post-MVP)
- Custom enterprise routing SLAs
