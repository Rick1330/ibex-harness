# MCP Memory Server (`services/mcp-memory`)

Python MCP resource server for tenant-scoped memory tools. The current surface uses Streamable HTTP, AuthService validation, memory HTTP calls, org-wide Redis rate limiting, metrics, and an asynchronous audit pipeline.

## Current contract

- **Transport:** Streamable HTTP at `/mcp`; stdio is local-only and must be disabled in production.
- **Auth:** Bearer token → `AuthService.ValidateToken`; rejects fail closed and are audited.
- **Tools:** `search_memory`, `write_memory`, and `record_feedback` through `IBEX_MEMORY_HTTP_URL` with `metadata.mcp_source=mcp_explicit`.
- **Rate limit:** org-wide Redis calendar-minute budget; over-limit returns `isError` / `rate_limited`. Development may use the explicit no-Redis exception; staging and production require Redis and return `rate_limit_unavailable` rather than admitting calls when Redis fails.
- **Probes:** `/health`, `/ready`, `/metrics`, and `/.well-known/oauth-protected-resource`.

## Audit durability boundary

Audit emission is asynchronous and fire-and-forget. When `IBEX_MCP_CLICKHOUSE_URL` is empty, the default `LoggingAuditSink` records metadata in logs only; it does **not** guarantee durable `ibex.mcp_tool_calls` rows. When the URL is configured, the ClickHouse HTTP sink writes to the provisioned table/migration, but a full queue can drop events and sink failures are observable rather than a durability guarantee. Treat audit evidence as incomplete unless the configured sink, retention, and restore path are verified.

## Configuration and production rules

| Variable | Purpose |
| --- | --- |
| `IBEX_AUTH_GRPC_ADDR` | AuthService target |
| `IBEX_MEMORY_HTTP_URL` | Memory service origin |
| `IBEX_MCP_REDIS_URL` / `IBEX_MCP_RATE_LIMIT_RPM` | Org rate limiting; Redis is required in staging/production |
| `IBEX_MCP_CLICKHOUSE_URL` | Optional durable audit sink |
| `IBEX_MCP_TRANSPORT` / `IBEX_MCP_ALLOW_STDIO` | Local transport selection; never enable stdio in production |

Production discovery/resource URLs must be public HTTPS, non-loopback, and bound to an approved origin. Do not infer OAuth authorization-server support from the discovery document.

## Local run and tests

```bash
cd services/mcp-memory
uv sync --frozen --extra dev
IBEX_AUTH_GRPC_ADDR=127.0.0.1:9091 .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8090

# from repository root
make test-mcp-memory
bash infra/scripts/mcp-memory-test-ci.sh
make test-clickhouse-migrate
```

See [ADR-0050](../../web/content/docs/adr/0050-mcp-server-skeleton.mdx). The service is not an OAuth authorization server and does not provide per-agent rate limits.
