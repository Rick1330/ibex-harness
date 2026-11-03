# MCP Memory Server

Living engineering notes for `services/mcp-memory/` ([ADR-0050](../engineering/adr/0050-mcp-server-skeleton.md)).

## Role

MCP **resource server** that exposes IBEX memory capabilities as audited tools.
Phase **2.5.G6.M1** ships transport + auth + stub tools. Phase **3.5** replaces stubs
with real pipelines; Phase **5** adds lineage tools.

It is **not** a general tool broker and **not** an OAuth authorization server.

## Boundaries

| Concern | Owner |
| --- | --- |
| Bearer validation | `AuthService.ValidateToken` gRPC (same identity as proxy) |
| Tenant scope | Token `org_id` only — never trust client-supplied org |
| Tool schemas | Explicit JSON Schema (`additionalProperties: false`) in `app/tools.py` |
| Persistence | None in G6; future writes go through memory write pipeline |
| Audit | Async emitter → `ibex.mcp_tool_calls` (no content columns). Empty `IBEX_MCP_CLICKHOUSE_URL` falls back to a logging sink; a full audit queue drops the event and increments a drop metric (tool call still succeeds). |

## Transport

- Production: Streamable HTTP at `/mcp` (`IBEX_MCP_TRANSPORT=streamable_http`)
- Dev/test: stdio only when `IBEX_MCP_TRANSPORT=stdio` **and** `IBEX_MCP_ALLOW_STDIO=true`
- Stdio is refused when `IBEX_ENV=production`

## Auth model

1. Client presents `Authorization: Bearer <token>`
2. MCP middleware validates via Auth gRPC with a short deadline (default 50ms)
3. Invalid/missing → HTTP 401 + `WWW-Authenticate` with `resource_metadata`
4. Auth outage/timeout → HTTP 503 (fail closed)
5. Tool permission bits: `MemoryRead` / `MemoryWrite` (ADR-0009)

Discovery: `GET /.well-known/oauth-protected-resource` advertises the protected resource
and authorization-server URL hint. Full AS flows remain downstream.

## Observability

- Probes: `GET /health` (liveness), `GET /ready` (auth reachability)
- Metrics: `GET /metrics` (Prometheus; includes audit drop/emit counters)
- Audit: never logs tokens or memory content — IDs + tool metadata only

## Extension points (later phases)

- 3.5.E.2 — replace stub runners with context/memory clients; keep schemas
- 3.5.E.3 — `record_feedback`
- 3.5.E.4 — independent MCP RPM (`isError`/`rate_limited`, not HTTP 429) + auth circuit-breaker polish (table already exists)
- 5.B.3 — `get_memory_lineage` (shipped, see below)

## Tools

| Tool | Permission | Memory call | Notes |
| --- | --- | --- | --- |
| `search_memory` | `MemoryRead` | `POST /v1/memories/search` | Org-scoped; `agent_id` resolves from the token or the argument |
| `write_memory` | `MemoryWrite` | `POST /v1/memories` | Content-hash idempotency key; `metadata.mcp_source=mcp_explicit` |
| `record_feedback` | `MemoryWrite` | `POST /v1/memories/{id}/feedback` | Agent-scoped tokens must pass `ValidateAgent` |
| `get_memory_lineage` | `MemoryRead` | `GET /v1/memories/{id}/lineage` | `max_depth` 1–5, default 3 |

`get_memory_lineage` returns the bounded relationship chain for one memory — both directions, all six edge types, plus
the supersession tip ([ADR-0094](adr/0094-bounded-lineage-and-conflict-suppression.md)). The depth cap and the cycle
break are enforced inside the traversal query, so the tool cannot ask for an unbounded walk. A memory outside the
caller's organization, or outside an agent-scoped token's agent, is a 404 from the memory service and surfaces as
`BackendRejectedError(code="not_found")` — the tool never returns an empty chain for something it cannot see.
`ISO-MCP-LINEAGE-01` covers the cross-tenant answer and a same-tenant control.

A memory-service `404` maps to `not_found` for **every** tool that names a memory id (`write_memory`,
`record_feedback`, `get_memory_lineage`), not only lineage. That is a deliberate 2026-11-03 change to the published
failure-code table: a missing or invisible entity is its own code instead of `backend_rejected`, so alerting and the
audit `error_code` column distinguish it from a malformed request.

## Local commands

```bash
make test-mcp-memory
cd services/mcp-memory && uv sync --extra dev
export IBEX_AUTH_GRPC_ADDR=127.0.0.1:9091
uvicorn app.main:app --host 127.0.0.1 --port 8090
```
