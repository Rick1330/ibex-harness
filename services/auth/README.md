# Auth service

Go service for IBEX Harness authentication. Exposes HTTP health/metrics and gRPC `AuthService.ValidateToken` ([ADR-0006](../../docs/adr/ADR-0006-auth-proto-contract.md), [ADR-0007](../../docs/adr/ADR-0007-auth-token-validation.md)).

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `GET /ready` | Readiness (Postgres TCP when `POSTGRES_DSN` set) |
| `GET /metrics` | Prometheus text metrics |
| gRPC `ibex.auth.v1.AuthService/ValidateToken` | Internal token validation |

## Configuration

See [.env.example](.env.example) and [ENVIRONMENT_VARIABLES.md](../../docs/ENVIRONMENT_VARIABLES.md) §10.

| Variable | Required | Default |
| --- | --- | --- |
| `POSTGRES_DSN` | Yes | — |
| `IBEX_PORT` | No | `8081` |
| `IBEX_GRPC_PORT` | No | `9091` |
| `IBEX_ARGON2_*` | No | see docs |

## Run locally

From repository root:

```bash
make compose-dev-up
make db-migrate
make proto-gen

IBEX_PORT=8081 IBEX_GRPC_PORT=9091 \
  POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable \
  go run ./services/auth/cmd/auth
```

## ValidateToken (grpcurl)

After seeding a PAT in Postgres (see integration tests or insert with `token.HashForTest` in a one-off script):

```bash
grpcurl -plaintext \
  -d '{"access_token":"ibex_pat_<uuid>_<secret>"}' \
  localhost:9091 ibex.auth.v1.AuthService/ValidateToken
```

## Tests

```bash
make proto-gen
go test ./services/auth/...
go test -tags=integration ./services/auth/...
```

Integration tests use `POSTGRES_TEST_DSN` (default port 5433 test compose) or the same DSN as dev on port 5432 in CI.

## Docker

```bash
docker build -f services/auth/Dockerfile .
```
