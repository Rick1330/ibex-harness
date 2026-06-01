# Proxy service

Go skeleton for the IBEX Harness LLM proxy service.

This service currently implements only platform endpoints:

- `GET /health` - liveness; no dependency checks
- `GET /ready` - readiness; checks Redis with `PING` when `REDIS_URL` is set
- `GET /metrics` - Prometheus text metrics for HTTP requests

No token validation, rate limiting, context injection, streaming, or provider proxying is implemented yet.

## Configuration

See [.env.example](.env.example).

| Variable | Required for startup | Required for readiness | Default |
| --- | --- | --- | --- |
| `IBEX_ENV` | No | No | `development` |
| `IBEX_SERVICE_NAME` | No | No | `proxy` |
| `IBEX_LOG_LEVEL` | No | No | `INFO` |
| `IBEX_PORT` | No | No | `8080` |
| `REDIS_URL` | No | Yes | empty |

## Run locally

From the repository root (single Go module):

```bash
IBEX_PORT=8080 REDIS_URL=redis://localhost:6379/0 go run ./services/proxy/cmd/proxy
```

Docker build (from repository root):

```bash
docker build -f services/proxy/Dockerfile .
```

## Verify

```bash
curl -s http://localhost:8080/health
curl -s http://localhost:8080/ready
curl -s http://localhost:8080/metrics
```

Expected missing-configuration readiness response:

```json
{"status":"not_ready","reason":"missing REDIS_URL"}
```
