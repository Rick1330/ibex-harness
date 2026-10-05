# Principal, Policy, and Run Contracts

**Status:** `specified`; implementation contract must be accepted before boundary expansion. The G0 packet is proposed in ADR-0084 and tracked by issue #933; this file does not claim G0 exit.

## PrincipalContext

Every request, internal RPC, worker job, MCP call, and evidence event carries a verified context containing:

- `org_id`, subject ID/type, and authentication source.
- `agent_id`, project/repository/session IDs when applicable.
- Purpose, data classification, residency, scopes, roles, and resource selectors.
- Policy epoch, trace ID, request ID, and deadline.
- Idempotency key and operation ID for mutations.

Caller-provided scope is a selector. AuthService and the enforcement plane derive authority from verified claims and policy; they do not trust arbitrary headers.

When a validated bearer token contains an `agent_id`, the selected agent must equal that token-bound identifier. A mismatch is an existence-safe authorization denial before target-agent lookup or downstream work. Organization-scoped tokens without an `agent_id` remain subject to the existing organization ownership and active-status checks. Any future cross-agent grant must be explicit, separately authenticated, resource-scoped, expiring, and auditable; it is not implied by organization membership. ADR-0084 records this proposed G0/G1 decision.

## PolicySnapshot

A request is evaluated against an immutable versioned snapshot containing permission rules, tool/provider constraints, data handling, budget policy, and effective epoch. The snapshot ID is recorded in evidence and carried into downstream calls.

## RunEnvelope

A run binds related requests, model attempts, context manifests, tool calls, async jobs, approvals, and evidence. It is not a permission grant. A run may be resumed only after revalidating principal, policy epoch, resource status, and approval expiry.

## Missing-state behavior

Missing identity, policy, resource ownership, policy epoch, or required scope is a security failure. The system must deny or return a typed service-degraded response before provider/tool work. Empty scope is not equivalent to verified no results when identity is ambiguous.
