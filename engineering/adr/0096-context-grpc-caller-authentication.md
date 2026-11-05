---
title: "ADR-0096: Authenticate ContextAssemblyService callers and derive tenant authority from the verified principal"
description: "Architecture decision record 0096: a shared caller token, principal-context binding, principal-derived directive keys, memory-hit tenant validation, and a loopback-only plaintext boundary."
adrId: "0096"
status: "Accepted"
date: "2026-11-05"
authors: "Elshaday Mengesha (@Rick1330)"
---

::decision-banner{status="Accepted" date="2026-11-05" id="0096"}
::

# ADR-0096: Authenticate ContextAssemblyService callers and derive tenant authority from the verified principal

- **Status:** Accepted
- **Date:** 2026-11-05
- **Authors:** Elshaday Mengesha (@Rick1330)
- **Depends on:** [ADR-0016](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0016-agent-identity-verification.md),
  [ADR-0038](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0038-context-assembly-service.md),
  [ADR-0071](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0071-context-grpc-degradation-deadline.md),
  [ADR-0084](https://github.com/Rick1330/ibex-harness/blob/main/engineering/adr/0084-g0-principal-agent-binding-and-idempotency.md)

## Context

`ContextAssemblyService` is reachable over `grpc.aio` on `IBEX_CONTEXT_GRPC_ADDR` (default `127.0.0.1:9092`) with no
caller authentication and no TLS. The servicer parsed `org_id` and `agent_id` from the request, and
`RedisDirectiveLookup` built the key `f"{org_id}:directive:{agent_id}"` from those values
(`services/context/app/clients/directive.py`). Any process that could reach the port could read another tenant's
directive by supplying its identifiers.

The proxy already builds `AssembleContextRequest.principal_context` from AuthService-verified data
(`services/proxy/internal/http/principal_context.go`) and its agent middleware returns HTTP 503 if it cannot build
one, so the principal is always present on the chat path. The message is unsigned; `PrincipalContextProof` is
reserved but unimplemented. The context server ignored the field entirely.

A synchronous `AuthService.ValidateToken` call at this boundary does not fit: the proxy client budget is 45 ms, the
server retrieval wall is 40 ms, and the established `ValidateToken` timeout is 50 ms. It would consume the assembly
budget and make context availability depend on AuthService, contradicting ADR-0071's degradation ownership.

The service has no Dockerfile, compose service, Helm template, or publish job. It runs as a host process on loopback.
The proxy dials it with TLS outside `development` while the server exposes only `add_insecure_port`, so a
staging/production deployment is not possible today.

## Decision

1. **Authenticate every RPC with a shared caller credential.** The proxy presents exactly one
   `x-ibex-context-service-token` metadata entry. The context server compares it with
   `IBEX_CONTEXT_GRPC_SERVICE_TOKEN` using `hmac.compare_digest` after a length check, rejects duplicate entries, and
   returns `UNAUTHENTICATED` with a constant message. The key is deliberately distinct from the auth service's
   `x-ibex-service-token`. No AuthService call is made on this path.
2. **Fail closed at startup.** The context server requires a 32–512 character `[A-Za-z0-9_-]` token, refuses a token
   equal to `IBEX_CONTEXT_MEMORY_API_TOKEN`, and refuses any bind that does not resolve exclusively to loopback. The
   proxy requires the same token when `IBEX_CONTEXT_ENABLED=true` and the target is non-empty, requires a loopback
   target, and refuses to enable context outside `development` while the server has no TLS. Neither side has a
   bypass flag.
3. **Treat `principal_context` as the authenticated caller's assertion, not as authorization.** The server requires
   the field, requires `authority == "AuthService"`, canonical `org_id`/`agent_id` UUIDs, and a bounded
   `principal_id`. `issued_at` is required within ±30 s. `expires_at` is optional, because AuthService omits it for
   non-expiring tokens; a present value older than 30 s is rejected.
4. **Bind the selectors and derive authority from the principal.** `org_id`/`agent_id` remain in the contract as
   selectors and must equal the principal; a mismatch is `PERMISSION_DENIED` before any Redis or memory call. The
   domain request is built from the principal, so the directive key cannot be caller-selected.
5. **Validate memory hits against the principal.** Every hit returned by the memory service must carry the
   principal's `org_id` and `agent_id`. One foreign hit fails that retrieval branch, is logged without content, and
   is never packed. Without this, a principal for org B with an agent from the memory credential's org could
   receive that org's memories.
6. **Disable gRPC port sharing.** The server is created with `("grpc.so_reuseport", 0)`. gRPC Python enables
   `SO_REUSEPORT` by default, which lets a same-UID process share the port and capture the token.
7. **Keep the degradation contract.** The proxy fails open on any `Assemble` error, applies its verified directive,
   and sets `X-IBEX-Context-Fallback: true`. Auth errors are logged at ERROR and counted; they are never retried.
8. **No proto wire change.** `context.proto` fields 1, 2, and 13 keep their tags and types; only comments describe
   the selector/authority split. `SearchMemories` and `RecordMemoryFeedback` still return `UNIMPLEMENTED` after
   authentication (ADR-0038); unauthenticated callers now receive `UNAUTHENTICATED` instead of learning which
   methods exist.

## Claim boundary

This decision closes **unauthenticated reachability**. It does **not** establish per-caller identity: the service
token is a shared secret and `PrincipalContext` is unsigned, so any token holder can assert any principal. Tenant
isolation remains a proxy-side property, and the status ledger must say so. Per-user validation at this boundary,
signed principals, policy-snapshot freshness, and TLS are separate decisions.

## Failure behaviour

| Condition | gRPC | Proxy | User |
|---|---|---|---|
| Missing, duplicate, or wrong token | `UNAUTHENTICATED` | fail open | chat succeeds with directive-only context; fallback header `true` |
| Server has no token | startup error; no listener | `UNAVAILABLE`; fail open | degraded; startup log names the variable |
| Non-loopback bind | startup error; no listener | `UNAVAILABLE`; fail open | degraded; prevents a plaintext credential on a network |
| Missing or malformed principal | `UNAUTHENTICATED` | fail open | degraded; alert |
| Expired or future principal | `UNAUTHENTICATED` | fail open | degraded; indicates clock skew or a stale request |
| Org or agent selector mismatch | `PERMISSION_DENIED` | fail open | degraded; audit log; zero downstream calls |
| Foreign memory hit | branch error, nothing packed | no fallback unless assembly fails | the foreign tenant's content never appears |
| Memory or Redis unavailable | `OK` with partial context | no fallback | memory-only or directive-only branch |
| AuthService unavailable | no effect on this hop | proxy returns 503 before context | the user sees the auth failure, not a context one |

## Consequences

**Positive.** The cross-tenant directive read is closed. No hot-path cost: one metadata scan and a constant-time
compare. No new dependency. AuthService availability is not coupled to this hop. The end-user bearer never reaches
the context service. Memory content is now tenant-checked at the second boundary as well.

**Negative.** A shared secret must be distributed, protected, and rotated; rotation is a coordinated restart with no
overlap window. A stolen token can assert any tenant. A compromised proxy can forge any principal, as it already
could. The boundary is plaintext and therefore loopback-only, which blocks container or networked deployment until
TLS exists. A wrong token degrades to directive-only and is visible only through logs, metrics, and alerts. Memory
retrieval remains scoped by the context service's memory credential, not by the principal; multi-tenant memory at
this boundary needs a separate decision.

## Alternatives considered

1. **Forward the end-user bearer and validate per request.** Rejected for this slice: a 50 ms `ValidateToken` call
   cannot fit the 40 ms wall; caching duplicates the proxy's revocation view; it couples context availability to
   AuthService and exposes the user bearer on another plaintext hop. It also does not validate the agent binding
   without `ValidateAgent`.
2. **Both.** Rejected: all of the above cost for a marginal gain that is weak without TLS.
3. **Keep loopback-only and document the risk.** Rejected: loopback is not an authorization boundary, and the
   directive read is real today.
4. **mTLS.** Deferred, not rejected: the correct long-term boundary, but it needs certificates, rotation, and a
   deployment profile that does not exist. The loopback rule keeps the plaintext token off the network until then.
5. **Sign `PrincipalContext` now.** Deferred: with a single authenticated caller the token already binds the
   assertion. Signing needs key management and a verifier and becomes necessary with a second caller or a relay.
6. **Remove the selector fields.** Rejected: a breaking proto change with no security benefit; the binding check is
   the control, and the fields remain useful for correlation.

## Compatibility and rollout

No database migration and no wire change. The server and proxy are built from the same checkout. When deployed
separately, restart the proxy first (it sends a header the old server ignores), then the context server. Roll back
in the opposite order, or set `IBEX_CONTEXT_ENABLED=false` to skip the client entirely. The new secret is required
only when context assembly is enabled.

## Evidence required

- Correct token, org-A principal, org-B selectors → `PERMISSION_DENIED`, directive lookup called zero times.
- Missing, duplicate, or wrong token → `UNAUTHENTICATED`, zero downstream calls.
- Missing, malformed, or expired principal → `UNAUTHENTICATED`.
- Agent mismatch → `PERMISSION_DENIED`.
- A foreign memory hit is never packed, in either branch.
- `SearchMemories` and `RecordMemoryFeedback`: no token → `UNAUTHENTICATED`; token → `UNIMPLEMENTED`.
- Startup refusals: missing or malformed token, memory-token reuse, non-loopback bind.
- Proxy config matrix: token required when enabled; non-loopback target rejected; non-development environment
  rejected; disabled needs neither.
- Exactly one metadata entry per call, and the auth-service header never crosses.
- The stub benchmark keeps a zero error rate, and the e2e negative leg asserts `UNAUTHENTICATED`.

## References

`services/context/app/{grpc_auth,principal,server,retrieval}.py`, `packages/contextclient/client.go`,
`services/proxy/internal/{config,bootstrap,http}`, `engineering/architecture-v2/03-contract-registry.md`.
