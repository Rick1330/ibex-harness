# ADR-0011: Proxy auth gRPC client and middleware

- **Status:** Accepted
- **Date:** 2026-06-04
- **Authors:** IBEX Harness team

## Context

Milestone 1.1.3 delivered auth `ValidateToken` ([ADR-0007](ADR-0007-auth-token-validation.md)). The proxy skeleton ([services/proxy](../../services/proxy/)) exposes health/metrics only. Milestone 1.2.1 connects the proxy to auth so protected routes receive `org_id` and permission context before LLM normalization (1.2.2).

[ARCHITECTURE.md](../ARCHITECTURE.md) describes a future bloom filter + LRU cache pipeline. Phase 2 optional milestone **2.2.1-auth-cache-bloom** owns that work; v1 uses remote validation only ([SECURITY.md](../SECURITY.md) §15: fail closed when validation cannot complete).

## Decision

### 1) Transport and connection

- gRPC to `ibex.auth.v1.AuthService/ValidateToken` ([ADR-0006](ADR-0006-auth-proto-contract.md))
- Single shared `*grpc.ClientConn` per proxy process; dial at startup; close on shutdown
- Development: insecure credentials; production: mTLS (documented follow-up, not in v1)

### 2) Timeouts

- Default per-validate timeout: **50ms** (`IBEX_AUTH_VALIDATE_TIMEOUT`)
- Use `context.WithTimeout` derived from the HTTP request context
- Exceeded deadline → HTTP **503** `SERVICE_DEGRADED` (fail closed)

### 3) Bearer parsing

- Read `Authorization: Bearer <token>`
- Strip the `Bearer` prefix and following space; pass PAT wire string (`ibex_pat_...`) as `ValidateTokenRequest.access_token`
- Missing header → HTTP **401** `MISSING_TOKEN`
- Invalid/revoked → HTTP **401** `INVALID_TOKEN` (maps gRPC `Unauthenticated`)

### 4) Request context

After successful validation, attach to `context.Context`:

- `org_id`, `permissions` (int64), optional `agent_id`, `user_id`, `token_id`

Handlers read via `auth.FromContext(ctx)`.

### 5) Permission and tenant checks

- Chat routes require `permissions.ProxyChatCompletion` ([ADR-0009](ADR-0009-permission-bitmap.md))
- Path-scoped routes (e.g. `/v1/orgs/{org_id}/...`) compare path `org_id` to token org → **403** on mismatch

### 6) HTTP error mapping

Minimal stable JSON envelope in `services/proxy/internal/errors/` (extended by milestone 1.2.3):

| Condition | HTTP | code |
| --- | --- | --- |
| Missing Authorization | 401 | `MISSING_TOKEN` |
| Invalid token | 401 | `INVALID_TOKEN` |
| Insufficient permissions / org mismatch | 403 | `INSUFFICIENT_PERMISSIONS` |
| Auth unreachable / timeout / internal | 503 | `SERVICE_DEGRADED` |

### 7) Cache (deferred)

- **Not implemented in v1**
- `auth.TokenValidator` interface allows a cache decorator in Phase 2 optional 2.2.1

### 8) Observability

- Metrics: `ibex_proxy_auth_validate_total`, `ibex_proxy_auth_validate_duration_seconds`
- Label: `result` only (`ok`, `unauthenticated`, `error`) — **no `org_id`**
- Logs: may include `org_id`, `token_id` after success; **never** log bearer or access_token

### 9) Middleware order

`metrics → logging → auth → handler` (future: body limit, rate limit before handler)

### 10) Public routes (no auth)

`/health`, `/ready`, `/metrics` remain unauthenticated.

## Consequences

### Positive

- Phase 1 exit criterion: proxy rejects unauthenticated traffic
- Clean extension point for auth cache in Phase 2

### Negative

- Every protected request hits auth gRPC (latency until cache milestone)
- 50ms budget may require tuning under load

## References

- [Milestone 1.2.1](../roadmap/phase-1-core-platform/milestones/1.2.1-proxy-auth-client.md)
- [ADR-0006](ADR-0006-auth-proto-contract.md)
- [ADR-0007](ADR-0007-auth-token-validation.md)
