---
title: API reference
description: HTTP and gRPC contracts for the proxy, management plane, auth service, and health surfaces.
audience: integrator
status: IMPLEMENTED
scope: shipped-local
verifiedDate: "2026-10-21"
sourceOfTruth: services/proxy; services/api; services/auth; packages/apierror
---

::page-status{status="IMPLEMENTED" verified="2026-10-21"}
::

IBEX exposes two HTTP planes and one internal gRPC plane. They have different authentication models and different stability guarantees.

| Plane | Owner | Auth | Status |
| --- | --- | --- | --- |
| Data plane | Go proxy | Bearer PAT + `X-IBEX-Agent-ID` | IMPLEMENTED |
| Management plane | Python API | Bearer PAT or operator session | PROVISIONAL |
| Internal identity | Go auth | gRPC caller identity; `ValidateToken` is private-network only | IMPLEMENTED |
| MCP | Python servers | Bearer PAT, tool-scoped permission bits | Mixed |

## Data plane

- [Chat completions](/docs/api-reference/chat-completions) — OpenAI-compatible chat, streaming, idempotency.
- [Responses](/docs/api-reference/responses) — Responses API subset, capability gates, and non-streaming limit.
- [Proxy health](/docs/api-reference/proxy-health) — `/health`, `/ready`, `/metrics`.
- [Errors](/docs/api-reference/errors) — stable envelope and code catalog.

## Management plane

- [Management API](/docs/api-reference/management-api) — organizations, users, agents, tokens, providers, budgets, policies, operator reads.
- [HTTP route inventory](/docs/api-reference/http-routes) — implemented route families and their boundaries.
- [Auth gRPC](/docs/api-reference/auth-grpc) — internal token, agent, and provider-credential methods.

## Conventions

- Tenant scope comes from the validated credential, not a client-supplied body field.
- Management paths include `org_id`; the path must match the credential's organization.
- Errors use the same JSON envelope on every HTTP plane.
- Cross-tenant resource identifiers return not-found semantics where enumeration is a risk.
- All timestamps are RFC 3339 UTC.
- Request IDs are UUID v4/v7 and are echoed in `X-Request-ID` and error bodies.

::callout
---
{"type":"warning","title":"Management routes are not a production operator contract"}
---

  Tenant-management routes are implemented locally. The operator session/read contract and Console remain provisional until hosted identity, origin, reconnect, redaction, and two-tenant evidence are accepted.

::
