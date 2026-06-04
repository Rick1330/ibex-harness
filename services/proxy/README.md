# Proxy service

Go service for the IBEX Harness LLM proxy.

## Platform endpoints (no auth)

- `GET /health` — liveness
- `GET /ready` — readiness; Redis `PING` when `REDIS_URL` is set
- `GET /metrics` — Prometheus text metrics

## Protected endpoints (Bearer PAT required)

- `GET /v1/internal/auth-probe` — returns `{org_id, permissions}` for the caller token
- `GET /v1/orgs/{org_id}/auth-probe` — same; **403** if path org ≠ token org
- `POST /v1/chat/completions` — auth + `ProxyChatCompletion` permission; returns **501** stub (provider not configured)

Auth validates via gRPC `ValidateToken` ([ADR-0011](../../docs/adr/ADR-0011-proxy-auth-client.md)). Fail closed: auth outage → **503**.

## Configuration

See [.env.example](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `IBEX_PORT` | `8080` | HTTP listen port |
| `REDIS_URL` | (empty) | Required for `/ready` when set |
| `IBEX_AUTH_GRPC_ADDR` | `127.0.0.1:9091` | Auth gRPC target |
| `IBEX_AUTH_VALIDATE_TIMEOUT` | `50ms` | Per-request validate budget |

## Run locally

Terminal 1 — auth (Postgres required):

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

## Verify

```bash
curl -s http://localhost:8080/health
curl -s -H "Authorization: Bearer <pat>" http://localhost:8080/v1/internal/auth-probe
```

## Tests

```bash
make proto-gen
go test ./services/proxy/...
go test -tags=integration ./services/proxy/...
```
