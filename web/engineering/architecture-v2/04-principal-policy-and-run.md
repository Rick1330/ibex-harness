# Principal, Policy, and Run Contracts

**Status:** `specified`; implementation contract must be accepted before boundary expansion. The G0 packet is proposed in ADR-0084 and tracked by issue #935; this file does not claim G0 exit.

## PrincipalContext

The target contract requires every request, internal RPC, worker job, MCP call, and evidence event to carry a verified context containing:

- `org_id`, subject ID/type, and authentication source.
- `agent_id`, project/repository/session IDs when applicable.
- Purpose, data classification, residency, scopes, roles, and resource selectors.
- Policy epoch, trace ID, request ID, and deadline.
- Idempotency key and operation ID for mutations.

Caller-provided scope is a selector. AuthService and the enforcement plane derive authority from verified claims and policy; they do not trust arbitrary headers.

### v1 field and trust freeze proposed by G0

The first additive mapping must carry, or bind by an authenticated server-side context, the following fields: `org_id`; subject ID and subject type; authentication source; selected `agent_id` and applicable project/repository/session selectors; purpose; data classification; residency; scopes/roles; policy snapshot ID/digest and effective epoch; trace ID; request ID; absolute deadline; idempotency key; and operation ID. Requiredness is contract-specific: identity, organization, auth source, policy epoch, trace/request IDs, and deadline are required on protected paths; resource selectors and mutation fields are required only for the operation class that uses them.

Callers may supply selectors, but never verified authority. The first mapping must reject missing, malformed, stale, forged, cross-organization, inactive, or token-bound-mismatched selectors before context retrieval, ranking, packing, provider, tool, or mutation work. The transport must distinguish authenticated claims from derived metadata and internal correlation fields; serialization must not allow a caller to overwrite verified values.

The v1 mapping is additive and, if separately approved after G0, is limited to one proxy-to-context seam. It does not claim that every worker, MCP, evidence, or provider boundary already carries this contract, and it does not introduce a durable run schema.

When a validated bearer token contains an `agent_id`, the selected agent must equal that token-bound identifier. A mismatch is an existence-safe authorization denial before target-agent lookup or downstream work. Organization-scoped tokens without an `agent_id` remain subject to the existing organization ownership and active-status checks. Any future cross-agent grant must be explicit, separately authenticated, resource-scoped, expiring, and auditable; it is not implied by organization membership. ADR-0084 records this proposed G0/G1 decision.

## PolicySnapshot

A request is evaluated against an immutable versioned snapshot containing permission rules, tool/provider constraints, data handling, budget policy, and effective epoch. The snapshot ID is recorded in evidence and carried into downstream calls.

The policy authority, snapshot digest, effective epoch, freshness/expiry, and behavior for missing, stale, or contradictory snapshots must be named in the accepted G0 registry. A cache, model output, retrieval score, memory text, tool description, or provider response cannot create or widen policy authority.

## RunEnvelope

A run binds related requests, model attempts, context manifests, tool calls, async jobs, approvals, and evidence. It is not a permission grant. A run may be resumed only after revalidating principal, policy epoch, resource status, and approval expiry.

For G0, this is a specified lineage contract only. Logical run ID, attempt ID, parent/fork relation, operation ID, and policy snapshot linkage must be distinguishable; retry/resume/fork must never reuse an attempt as if it were a new authorization. Durable storage, replay, approval consumption, and cross-boundary implementation remain explicitly deferred until separately accepted.

## Transport trust mapping proposed by G0

| Boundary | Verified authority source | Caller-controlled selectors | Required failure behavior |
|---|---|---|---|
| HTTP to proxy | AuthService validation plus enforcement policy | Agent/project/session/resource IDs | Deny/503 before downstream work |
| Proxy to context | Server-bound PrincipalContext v1 | Context request selectors only | Reject mismatch or unavailable verifier; no permissive fallback |
| Worker job | Authenticated operation/run envelope | Job payload references | Revalidate tenant/resource/policy before mutation |
| MCP | Resource-server principal plus tool registry/policy | Tool arguments and resource IDs | Deny before memory/effect call; no existence leak |
| Evidence | Server-generated operation/event envelope | None for authority fields | Reject unscoped/unredacted payloads before persistence/sink |

This matrix is proposed, not accepted, until owners sign the G0 packet and the status ledger records the decision.

## Missing-state behavior

Missing identity, policy, resource ownership, policy epoch, or required scope is a security failure. The system must deny or return a typed service-degraded response before provider/tool work. Empty scope is not equivalent to verified no results when identity is ambiguous.
