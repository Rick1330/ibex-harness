# Proxy service

Go service for the IBEX Harness LLM proxy.

## Platform endpoints (no auth)

- `GET /health` — liveness
- `GET /ready` — readiness; Redis `PING` when `REDIS_URL` is set
- `GET /metrics` — Prometheus text metrics

## Protected endpoints (Bearer PAT + agent header required)

All protected routes require:

- `Authorization: Bearer <pat>`
- `X-IBEX-Agent-ID: <uuid>` — must be an **active** agent owned by the token's org ([ADR-0016](../../docs/adr/ADR-0016-agent-identity-verification.md))

- `GET /v1/internal/auth-probe` — returns `{org_id, permissions}` for the caller token
- `GET /v1/orgs/{org_id}/auth-probe` — same; path `org_id` must be UUID; **403** if path org ≠ token org
- `POST /v1/chat/completions` — auth + agent verify + `ProxyChatCompletion`; body limit + JSON Content-Type; semantic validation; rate limit; **501** when valid; **429** `RATE_LIMITED`; **400** `MISSING_AGENT_ID` / `VALIDATION_ERROR` / `INVALID_JSON`; **403** `AGENT_NOT_AUTHORIZED` / `AGENT_SUSPENDED`; **413** / **415** per [ADR-0013](../../docs/adr/ADR-0013-proxy-input-validation-and-error-envelope.md)

Auth validates via gRPC `ValidateToken` ([ADR-0011](../../docs/adr/ADR-0011-proxy-auth-client.md)). Agent ownership via gRPC `ValidateAgent` ([ADR-0016](../../docs/adr/ADR-0016-agent-identity-verification.md)). Parse: [ADR-0012](../../docs/adr/ADR-0012-proxy-request-normalization.md). Validation + envelope: [ADR-0013](../../docs/adr/ADR-0013-proxy-input-validation-and-error-envelope.md). Rate limit: [ADR-0015](../../docs/adr/ADR-0015-proxy-rate-limit-skeleton.md). Fail closed: token auth outage → **503** `SERVICE_DEGRADED`; agent verify outage → **503** `AUTH_UNAVAILABLE`. Rate limit Redis outage → fail open (request allowed).

## Middleware order

```text
metrics → requestContext → responseHeaders → logging → mux

POST /v1/chat/completions:
  bodyLimit → contentType → auth → agentVerify → rateLimit → handler

GET /v1/internal/auth-probe:
  auth → agentVerify → rateLimit → handler

GET /v1/orgs/{org_id}/auth-probe:
  pathOrgUUID → auth → agentVerify → rateLimit → handler
```

Protected responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` when rate limiting is enabled. **429** responses also include `Retry-After`.

All responses include `X-Request-ID`, `X-Trace-ID`, and `X-Response-Time` (configurable header names via env).

## Configuration

See [.env.example](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `IBEX_PORT` | `8080` | HTTP listen port |
| `REDIS_URL` | (empty) | Required for `/ready` when set |
| `IBEX_AUTH_GRPC_ADDR` | `127.0.0.1:9091` | Auth gRPC target |
| `IBEX_AUTH_VALIDATE_TIMEOUT` | `50ms` | Per-request validate budget |
| `IBEX_MAX_REQUEST_BODY_BYTES` | `1048576` | Chat body cap (1 MiB) |
| `IBEX_REQUEST_ID_HEADER` | `X-Request-ID` | Incoming/outgoing request ID |
| `IBEX_TRACE_ID_HEADER` | `X-Trace-ID` | Trace ID header |
| `IBEX_ERROR_DOCS_BASE` | (empty) | Optional `docs_url` prefix |
| `IBEX_RATE_LIMIT_DEFAULT_RPM` | `60` | Org requests per minute |
| `IBEX_RATE_LIMIT_ORG_OVERRIDES` | (empty) | `uuid=rpm,uuid2=rpm2` |

## Run locally

Start **auth first**, then proxy. Chat requires a real PAT with `ProxyChatCompletion` permission (create via [auth CreateToken](../auth/README.md#grpc-examples-grpcurl) — replace `<pat>` below).

### Bash

Terminal 1 — auth:

```bash
make compose-dev-up && make db-migrate
POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable \
  IBEX_GRPC_PORT=9091 go run ./services/auth/cmd/auth
```

Terminal 2 — proxy:

```bash
IBEX_AUTH_GRPC_ADDR=127.0.0.1:9091 REDIS_URL=redis://localhost:6379/0 \
  go run ./services/proxy/cmd/proxy
```

### Windows (PowerShell)

Terminal 1 — auth:

```powershell
cd D:\ibex-r\ibex-harness
make compose-dev-up
make db-migrate
$env:POSTGRES_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
$env:IBEX_GRPC_PORT = "9091"
go run ./services/auth/cmd/auth
```

Terminal 2 — proxy (new window; auth must stay running):

```powershell
cd D:\ibex-r\ibex-harness
$env:IBEX_AUTH_GRPC_ADDR = "127.0.0.1:9091"
$env:REDIS_URL = "redis://localhost:6379/0"
go run ./services/proxy/cmd/proxy
```

## Verify

```bash
curl -s http://localhost:8080/health
curl -s -H "Authorization: Bearer <pat>" -H "X-IBEX-Agent-ID: <agent-uuid>" http://localhost:8080/v1/internal/auth-probe
```

Chat (bash):

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Authorization: Bearer <pat>" \
  -H "Content-Type: application/json" \
  -H "X-IBEX-Agent-ID: 550e8400-e29b-41d4-a716-446655440000" \
  -d '{"model":"gpt-4","messages":[{"role":"user","content":"hello"}]}'
# expect 501 PROVIDER_NOT_CONFIGURED
```

Chat (PowerShell — do not use bash `\` line continuation):

```powershell
$headers = @{
  Authorization = "Bearer <pat>"
  "Content-Type" = "application/json"
  "X-IBEX-Agent-ID" = "550e8400-e29b-41d4-a716-446655440000"
}
$body = '{"model":"gpt-4","messages":[{"role":"user","content":"hello"}]}'
Invoke-RestMethod -Uri http://localhost:8080/v1/chat/completions -Method POST -Headers $headers -Body $body
```

Validation error example (**400**):

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "request_id": "...",
    "timestamp": "...",
    "field_errors": [
      { "field": "model", "code": "REQUIRED", "message": "model is required" }
    ]
  }
}
```

## Tests

```bash
make proto-gen
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
```

**Windows integration tests** — default Postgres is port **5433** (`make compose-test-up`), or point at dev Postgres on **5432**:

```powershell
make compose-test-up
go test -tags=integration ./services/proxy/...

# Or reuse compose-dev-up Postgres:
$env:POSTGRES_TEST_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
go test -tags=integration ./services/proxy/...
```
