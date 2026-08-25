# MCP Memory Server

Living engineering notes for `services/mcp-memory/` ([ADR-0050](../content/docs/adr/0050-mcp-server-skeleton.mdx)).

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
- 3.5.E.4 — independent MCP RPM + auth circuit-breaker polish (table already exists)
- 5.B.3 — `get_memory_lineage`

## Local commands

```bash
make test-mcp-memory
cd services/mcp-memory && uv sync --extra dev
export IBEX_AUTH_GRPC_ADDR=127.0.0.1:9091
uvicorn app.main:app --host 127.0.0.1 --port 8090
```
