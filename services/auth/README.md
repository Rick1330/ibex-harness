# Auth service

Go service for IBEX Harness authentication. Exposes HTTP health/metrics and gRPC `AuthService` ([ADR-0006](../../web/content/docs/adr/0006-auth-proto-contract.mdx), [ADR-0007](../../web/content/docs/adr/0007-auth-token-validation.mdx), [ADR-0009](../../web/content/docs/adr/0009-permission-bitmap.mdx)).

## Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness — `{"status":"ok","checks":{}}` ([ADR-0022](../../web/content/docs/adr/0022-health-check-contract.mdx)) |
| `GET /ready` | Readiness — critical: `postgres` (`SELECT 1`), `grpc` (TCP) |
| `GET /metrics` | Prometheus text metrics |
| gRPC `ValidateToken` | Internal token validation (no caller bearer). **Private-network only** — listen for trusted proxy hosts (mTLS / internal net). `IBEX_AUTH_VALIDATE_RPM` is a per-proxy-host aggregate cap when `REDIS_URL` is set (disabled when Redis is empty); it is **not** client-facing internet rate limiting. Constant-cost miss path. |
| gRPC `ValidateAgent` | Checks `agent_id` belongs to token `org_id` and is active (called by proxy after `ValidateToken`) |
| gRPC `CreateToken` / `RevokeToken` / `ListTokens` | PAT lifecycle (caller bearer required) |

## Configuration

See [.env.example](.env.example) and [ENVIRONMENT_VARIABLES.md](../../web/engineering/ENVIRONMENT_VARIABLES.md) §10.

| Variable | Required | Default |
| --- | --- | --- |
| `POSTGRES_DSN` | Yes | — |
| `REDIS_URL` | No | empty (disables revoke pub/sub + ValidateToken RPM) |
| `IBEX_AUTH_VALIDATE_RPM` | No | `6000` (per proxy-host aggregate) |
| `IBEX_PORT` | No | `8081` |
| `IBEX_GRPC_PORT` | No | `9091` |
| `IBEX_ARGON2_*` | No | see docs |

**Next (Phase 4 planning baseline):** provider-credential RPCs for BYO keys (encrypted at rest; proxy resolves via Auth gRPC — never plaintext in API responses). Exact RPC/env names land with that milestone + ADR. Full env registry: [ENVIRONMENT_VARIABLES.md](../../web/engineering/ENVIRONMENT_VARIABLES.md).

## Testing

```bash
# Unit (no infra)
go test ./services/auth/...

# Integration (Postgres; covered by CI auth-validate-smoke)
# Includes peer ValidateToken RPM + oversized PAT guards via miniredis/Postgres.
make compose-test-up
go test -tags=integration ./services/auth/...
```

There is no dedicated compose E2E workflow for ValidateToken RPM: merge gates already run the integration suite above. Live compose smoke remains `make e2e-wave2b-token-fks` / `make dev-smoke` (make-only, not CI).

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

**Windows (PowerShell)** — use `$env:` instead of bash `VAR=value cmd` (no `\` line continuation).
Set `$RepoRoot` to your clone path first:

```powershell
$RepoRoot = 'C:\path\to\ibex-harness'   # set to your clone
Set-Location $RepoRoot
make compose-dev-up
make db-migrate
make proto-gen
$env:POSTGRES_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
$env:IBEX_GRPC_PORT = "9091"
go run ./services/auth/cmd/auth
```

## gRPC examples (grpcurl)

**ValidateToken** (no authorization metadata):

```bash
grpcurl -plaintext \
  -d '{"access_token":"ibex_pat_<uuid>_<secret>"}' \
  localhost:9091 ibex.auth.v1.AuthService/ValidateToken
```

**CreateToken** (requires caller PAT with `TokenCreate`; requested permissions must be a
subset of the caller bitmap; optional `agent_id` / `user_id` must belong to `org_id`):

```bash
grpcurl -plaintext \
  -H "authorization: Bearer ibex_pat_<admin-uuid>_<secret>" \
  -d '{"org_id":"<org-uuid>","name":"dev-pat","type":1,"permissions":23}' \
  localhost:9091 ibex.auth.v1.AuthService/CreateToken
```

Store the returned `plaintext` immediately; it cannot be retrieved again.

**RevokeToken**:

```bash
grpcurl -plaintext \
  -H "authorization: Bearer ibex_pat_<admin-uuid>_<secret>" \
  -d '{"org_id":"<org-uuid>","token_id":"<token-uuid>"}' \
  localhost:9091 ibex.auth.v1.AuthService/RevokeToken
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
