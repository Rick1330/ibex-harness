# Auth service

Go skeleton for the IBEX Harness auth service.

This service currently implements only platform endpoints:

- `GET /health` - liveness; no dependency checks
- `GET /ready` - readiness; checks Postgres connectivity when `POSTGRES_DSN` is set
- `GET /metrics` - Prometheus text metrics for HTTP requests

No token creation, JWT validation, permission checks, or auth business logic is implemented yet.

## Configuration

See [.env.example](.env.example).

| Variable | Required for startup | Required for readiness | Default |
| --- | --- | --- | --- |
| `IBEX_ENV` | No | No | `development` |
| `IBEX_SERVICE_NAME` | No | No | `auth` |
| `IBEX_LOG_LEVEL` | No | No | `INFO` |
| `IBEX_PORT` | No | No | `8081` |
| `POSTGRES_DSN` | No | Yes | empty |

## Run locally

From the repository root (single Go module):

```bash
IBEX_PORT=8081 POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex go run ./services/auth/cmd/auth
```

Docker build (from repository root):

```bash
docker build -f services/auth/Dockerfile .
```

## Verify

```bash
curl -s http://localhost:8081/health
curl -s http://localhost:8081/ready
curl -s http://localhost:8081/metrics
```

Expected missing-configuration readiness response:

```json
{"status":"not_ready","reason":"missing POSTGRES_DSN"}
```
