# MCP Memory Server (`services/mcp-memory`)

Python MCP **resource server** for IBEX memory tools (Phase **2.5.G6.M1** skeleton).

- Transport: Streamable HTTP (`/mcp`); stdio only when `IBEX_MCP_TRANSPORT=stdio` and `IBEX_MCP_ALLOW_STDIO=true`
- Auth: Bearer → `AuthService.ValidateToken` gRPC (fail closed)
- Tools: stub `search_memory` / `write_memory` (no persistence)
- Audit: async `ibex.mcp_tool_calls` emitter seam (ClickHouse)

See [ADR-0050](../../web/content/docs/adr/0050-mcp-server-skeleton.mdx).

## Local run

```bash
cd services/mcp-memory
uv sync --extra dev
export IBEX_AUTH_GRPC_ADDR=127.0.0.1:9091
uvicorn app.main:app --host 127.0.0.1 --port 8090
```

Probes: `GET /health`, `GET /ready`, discovery `GET /.well-known/oauth-protected-resource`.

## Tests

```bash
make test-mcp-memory
# or
bash infra/scripts/mcp-memory-test-ci.sh
```

ClickHouse migration tests live under `infra/migrations/clickhouse/` at the **repo root** — do not run `go test ./infra/migrations/clickhouse/` from this directory (paths are cwd-relative). Use:

```bash
make test-clickhouse-migrate
# integration (compose-test ClickHouse on localhost:9003):
make test-clickhouse-migrate-integration
```

## Non-goals (this milestone)

- Real memory pipelines (Phase 3.5.E.2)
- Feedback / lineage tools
- OAuth authorization server
