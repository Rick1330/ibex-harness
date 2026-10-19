# IBEX MCP Operator Gateway (`services/mcp-operator`)

Read-only MCP resource server for operators (GAP-009). It exposes four
metadata-only tools over Streamable HTTP, gated by bearer auth and the shared
enforcement pipeline in [`packages/mcp_gateway`](../../packages/mcp_gateway). See
[ADR-0086](../../web/content/docs/adr/0086-mcp-operator-gateway.mdx).

**Default off.** The process serves only `/health`, `/ready`, and `/metrics`
until `IBEX_MCP_OPERATOR_ENABLED=true`. Transport is Streamable HTTP only; stdio
is not implemented by this service.

## Tools

| Tool | Scope | Permission bit | Returns |
| --- | --- | --- | --- |
| `session.get` | `operator.read` | `OPERATOR_METADATA_READ` | Redacted session metadata |
| `run.get` | `runs.read` | `TRACE_READ` | Redacted evidence-run metadata |
| `evidence.query` | `evidence.read` | `OPERATOR_REDACTED_READ` | Redacted evidence-run list |
| `budget.get` | `budget.read` | `BILLING_READ` | Budget periods (cached cents) |

All tools are `read_only`. No mutating tool can be registered. No tool accepts an
`org_id`/`agent_id` argument — identity comes only from the validated token.

## Enforcement order (fail closed)

`resolve tool → authorize (bitmap) → validate args → org rate limit → timed read →
redact → audit`. Every failure maps to a typed code (`permission_denied`,
`not_found`, `invalid_params`, `rate_limited`, `backend_unavailable`, …). Unknown
or cross-tenant resources return `not_found` (404 semantics), never
`permission_denied`, to avoid existence leaks.

## Authorization caveat (must remain visible)

Authorization is a bitmap check on the AuthService-validated token. The
PolicySnapshot resource/action evaluator of `mcp-gateway-policy.v1` is **not**
wired to a Python verifier, so a `PolicyEvaluator` seam is the only extension
point today. This hole is tracked in GAP-009 and the contract registry; it is not
closed by this service.

## Run locally

```bash
uv sync --all-extras
IBEX_ENV=development \
IBEX_MCP_OPERATOR_ENABLED=true \
IBEX_MCP_OPERATOR_DATABASE_URL=postgresql+asyncpg://ibex_app:ibex_app@127.0.0.1:5432/ibex \
IBEX_AUTH_GRPC_ADDR=127.0.0.1:9091 \
uv run uvicorn app.main:app --host 127.0.0.1 --port 8091
```

See [`.env.example`](.env.example) for every setting.

## Tests

```bash
uv run pytest -q                      # unit (no DB)
uv run pytest -m integration -q       # live PostgreSQL (RLS + cross-tenant)
```

Integration tests skip unless a PostgreSQL URL is configured via
`IBEX_MCP_OPERATOR_TEST_DATABASE_URL` (or `IBEX_DATABASE_URL`/`DATABASE_URL`).
