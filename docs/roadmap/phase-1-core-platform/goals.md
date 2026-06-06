# Phase 1 — Goals

## Goal 1.0: Test infrastructure (prerequisite)

**Description:** Shared Go integration test harness (testcontainers, tags, CI) before auth/proxy integration milestones scale up.

**Related milestones:**

- [1.0.1](milestones/1.0.1-go-integration-test-infrastructure.md)

**Validation:** `go test -tags=integration ./...` documented and runnable in CI smoke path

---

## Goal 1.1: Persistence and auth data plane

**Description:** Introduce Postgres migrations and the minimum schema for organizations and API tokens, plus the auth gRPC contract and validation logic.

**Acceptance criteria:**

- Migration runner integrated with `Makefile` / `dev-tool.sh`
- Tables match subset of [DATABASE_SCHEMA.md](../../DATABASE_SCHEMA.md) (`ibex_core.organizations`, `ibex_core.tokens`)
- RLS enabled; `SET LOCAL app.current_org_id` pattern documented and tested
- `ValidateToken` (or equivalent) RPC returns org_id + permission bitmap or unauthenticated error
- Cross-tenant test: token from Org A cannot validate as Org B

**Related milestones:**

- [1.1.1](milestones/1.1.1-postgres-migrations.md)
- [1.1.2](milestones/1.1.2-auth-proto-and-codegen.md)
- [1.1.3](milestones/1.1.3-auth-token-validation.md)
- [1.1.4](milestones/1.1.4-token-creation-and-management-api.md)
- [1.1.5](milestones/1.1.5-permission-bitmap-contract-and-adr.md)
- [1.1.6](milestones/1.1.6-argon2id-parameters-and-crypto-policy-adr.md)
- [1.1.7](milestones/1.1.7-users-and-agents-schema.md)

**Validation:** `make db-migrate`; `go test ./services/auth/...` with integration tag; grpcurl or integration client against auth

---

## Goal 1.2: Proxy platform integration

**Description:** Wire the proxy to auth and parse incoming LLM requests without calling a provider.

**Acceptance criteria:**

- Proxy calls auth with bounded timeout; fails closed on auth errors
- Valid request attaches org context for downstream use (no provider call yet)
- OpenAI-shaped chat completion JSON parses; malformed body → 400 with stable error envelope
- No new business endpoints beyond documented proxy routes for this goal

**Related milestones:**

- [1.2.1](milestones/1.2.1-proxy-auth-client.md)
- [1.2.2](milestones/1.2.2-proxy-request-normalization.md)
- [1.2.3](milestones/1.2.3-proxy-input-validation-and-stable-error-envelope.md)
- [1.2.4](milestones/1.2.4-proxy-rate-limit-skeleton.md)
- [1.2.5](milestones/1.2.5-proxy-agent-identity-verification.md)
- [1.2.6](milestones/1.2.6-request-id-correlation-middleware.md)
- [1.2.7](milestones/1.2.7-graceful-shutdown.md)

**Validation:** Integration tests with auth + proxy running; httptest for malformed payloads

---

## Goal 1.3: Observability baseline

**Description:** Align skeleton observability with [MONITORING.md](../../MONITORING.md) and [DEPENDENCIES.md](../../DEPENDENCIES.md).

**Acceptance criteria:**

- OTel tracer/meter providers initialized in auth and proxy `main` (exporter optional)
- HTTP middleware creates spans for request path
- Migrate `/metrics` to `prometheus/client_golang` OR document ADR deferral with parity tests
- Logs remain structured JSON; no secrets or raw memory content

**Related milestones:**

- [1.3.1](milestones/1.3.1-otel-tracer-provider-init.md)
- [1.3.2](milestones/1.3.2-prometheus-metric-catalog.md)
- [1.3.3](milestones/1.3.3-shared-logger-package.md)

---

## Goal 1.4: Developer experience baseline

**Description:** Canonical local dev onboarding: idempotent seed data, `.env.example` files, local smoke tests, shared config/error packages, and a standardised health check contract.

**Acceptance criteria:**

- `make db-seed` produces a working org, user, agent, and PAT on a migrated dev database
- `make dev-smoke` validates auth → proxy without an LLM key
- `packages/config` and `packages/apierror` are used by auth and proxy (no scattered `os.Getenv` for required vars)
- `/health` and `/ready` follow a documented JSON contract across Go services

**Related milestones:**

- [1.4.1](milestones/1.4.1-developer-experience-baseline.md)
- [1.4.2](milestones/1.4.2-shared-config-and-error-packages.md)
- [1.4.3](milestones/1.4.3-health-check-contract.md)

**Validation:** Fresh clone + `make compose-dev-up` + `make db-migrate` + `make db-seed` + `make dev-smoke` exits 0

---

## Goal 1.5: Phase 1 security gate

**Description:** End-to-end security integration test suite validating the composed proxy middleware chain (auth → agent verify → rate limit) against real Postgres and Redis. Explicit Phase 1 completion gate.

**Acceptance criteria:**

- Token from Org A cannot access Org B resources (403)
- Revoked token rejected (401) within documented SLA
- Cross-org agent ID rejected (403)
- Rate limit returns 429 with `Retry-After`
- Insufficient permission bitmap returns 403
- All tests run under `go test -tags=integration` in CI

**Related milestones:**

- [1.5.1](milestones/1.5.1-security-integration-test-suite.md)

**Validation:** `go test -tags=integration ./services/proxy/...` security suite green; Phase 1 exit criteria in README satisfied

---

## Decision points (mid-phase)

| When | Question | Default if no pivot |
| --- | --- | --- |
| After 1.1.1 | golang-migrate vs goose vs atlas | golang-migrate (ADR-0005) |
| After 1.1.2 | gRPC only vs internal HTTP for auth | gRPC per ARCHITECTURE.md |
| After 1.2.1 | In-process auth vs always remote | Remote gRPC with short timeout |

Log pivots in [FINDINGS.md](../FINDINGS.md).
