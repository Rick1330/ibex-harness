---
title: MCP
description: Tenant-scoped memory tools and the default-off read-only operator gateway.
audience: integrator
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-10-21"
sourceOfTruth: services/mcp-memory; services/mcp-operator; packages/mcp_gateway
---

::page-status{status="PROVISIONAL" verified="2026-10-21" note="Memory MCP audit is provisional; operator gateway is default-off"}
::

IBEX exposes two MCP servers with deliberately different risk profiles:

- **Memory MCP** — search, write, and feedback tools for agent memory.
- **Operator MCP** — four metadata-only read tools for session, run, evidence, and budget inspection.

## Pages

- [Memory server](/docs/mcp/memory-server) — Streamable HTTP, auth, tools, rate limits, audit boundary.
- [Operator gateway](/docs/mcp/operator-gateway) — read-only tools, enforcement order, and the policy-evaluator gap.

## Shared rules

| Rule | Why |
| --- | --- |
| Streamable HTTP for deployed use | stdio is local-only and must be disabled in production |
| Identity comes from the validated token | Tools do not accept `org_id` or `agent_id` arguments |
| Every call is tenant-scoped | Cross-tenant resources return not-found semantics |
| Org rate limits apply before tool execution | Unauthorized calls cannot bypass the budget |
| Unknown tools do not reveal existence | `tool_not_found`, not `permission_denied` |
| Audit is not automatically durable | A configured sink still has queue-drop and failure modes |

::callout
---
{"type":"danger","title":"stdio is not a production transport"}
---

  Do not enable stdio for a deployed MCP server. Do not expose a local-only transport as a network service.

::

## Status

| Server | Transport | Status | Boundary |
| --- | --- | --- | --- |
| Memory MCP | Streamable HTTP | PROVISIONAL | Audit is logging-first; rate limiting requires Redis in staging/production |
| Operator MCP | Streamable HTTP | IMPLEMENTED | Default-off; PolicySnapshot resource evaluation is not wired |
