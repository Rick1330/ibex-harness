# ADR-0016: Proxy agent identity verification (Phase 1)

- **Status:** Accepted
- **Date:** 2026-06-06
- **Authors:** IBEX Harness team

## Context

Milestone 1.2.3 extracts `X-IBEX-Agent-ID` as a parseable UUID but does not verify that the agent belongs to the authenticated organization. An Org A token combined with Org B's agent UUID creates a cross-tenant confusion risk. Auth service M1.1.7 already implements `ValidateAgent` gRPC; the proxy must call it on every protected request.

## Decision

### 1) Enforcement point

Agent ownership is verified in the **proxy middleware**, not in downstream memory/context services. Rationale:

- Single enforcement point before any handler runs
- Latency cost is already paid for token validation on the same gRPC connection
- Downstream services receive a verified `AgentRecord` in context

### 2) gRPC to auth, not direct DB

Proxy calls `AuthService.ValidateAgent` via the existing `*grpc.ClientConn`. Proxy must **not** query Postgres for agents.

### 3) Bearer forwarding

`ValidateAgent` requires caller authentication (auth unary interceptor). Proxy re-parses the `Authorization` header and forwards `authorization: Bearer <token>` as outgoing gRPC metadata. Tokens are never logged.

### 4) org_id source

`org_id` passed to `ValidateAgent` comes from `auth.FromContext` (token claims), never from the request body, URL, or `X-IBEX-Agent-ID` header alone.

### 5) Required header

`X-IBEX-Agent-ID` is **required** on all protected Phase-1 routes:

- `GET /v1/internal/auth-probe`
- `GET /v1/orgs/{org_id}/auth-probe`
- `POST /v1/chat/completions`

### 6) Anti-enumeration

Auth returns `PERMISSION_DENIED` (not `NOT_FOUND`) for cross-org and missing agents. Proxy maps to **403** `AGENT_NOT_AUTHORIZED` — never **404**.

Inactive agents (`paused`, `suspended`, `archived`) return `PERMISSION_DENIED` with message `"agent is not active"`. Proxy maps to **403** `AGENT_SUSPENDED`. Other `PERMISSION_DENIED` cases map to `AGENT_NOT_AUTHORIZED`.

### 7) Fail-closed vs fail-open

| Control | Failure behavior | HTTP | `code` |
| --- | --- | --- | --- |
| Token validate (M1.2.1) | Fail closed | 503 | `SERVICE_DEGRADED` (ADR-0011; unchanged) |
| Agent verify (M1.2.5) | Fail closed | 503 | `AUTH_UNAVAILABLE` |
| Rate limit (M1.2.4) | Fail open | — | — |

Agent identity is a security control; failing open during auth downtime would allow cross-tenant agent confusion.

### 8) HTTP mapping (agent middleware)

| Condition | HTTP | `code` |
| --- | --- | --- |
| Header absent | 400 | `MISSING_AGENT_ID` |
| Malformed UUID | 400 | `VALIDATION_ERROR` + `field_errors` |
| Cross-org / not found | 403 | `AGENT_NOT_AUTHORIZED` |
| Inactive agent | 403 | `AGENT_SUSPENDED` |
| gRPC timeout / transport error | 503 | `AUTH_UNAVAILABLE` |

### 9) Middleware order

Amends [ADR-0013](ADR-0013-proxy-input-validation-and-error-envelope.md) §8 and [ADR-0015](ADR-0015-proxy-rate-limit-skeleton.md) §6:

```text
POST /v1/chat/completions:
  bodyLimit → contentType → auth → agentVerify → rateLimit → handler

GET /v1/internal/auth-probe:
  auth → agentVerify → rateLimit → handler

GET /v1/orgs/{org_id}/auth-probe:
  pathOrgUUID → auth → agentVerify → rateLimit → handler
```

### 10) Context

Verified agent stored as `AgentRecord{ID, OrgID, Status}` via `AgentFromContext`. Chat handler no longer validates agent header (middleware owns it).

### 11) Phase 2 caching (deferred)

Same pattern as token validation: bloom filter → LRU → gRPC fallback (milestone 2.2.1).

### 12) Configuration

Reuses `IBEX_AUTH_VALIDATE_TIMEOUT` (default 50ms) for `ValidateAgent` per-call deadline on the shared auth gRPC client.

## Consequences

### Positive

- Closes cross-tenant agent confusion attack
- Consistent with multi-tenant security rules (403 not 404)
- Reuses auth service as source of truth

### Negative

- Second gRPC call per protected request (mitigated by shared connection; Phase 2 cache planned)
- `AGENT_SUSPENDED` mapping relies on stable auth gRPC message `"agent is not active"` until richer error details exist

## References

- [Milestone 1.2.5](../roadmap/phase-1-core-platform/milestones/1.2.5-proxy-agent-identity-verification.md)
- [ADR-0011](ADR-0011-proxy-auth-client.md)
- [ADR-0013](ADR-0013-proxy-input-validation-and-error-envelope.md)
- [ADR-0015](ADR-0015-proxy-rate-limit-skeleton.md)
