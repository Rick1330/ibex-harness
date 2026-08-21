# Proxy service

Go service for the IBEX Harness LLM proxy.

## Platform endpoints (no auth)

- `GET /health` — liveness (`{"status":"ok","checks":{}}`; [ADR-0022](../../web/content/docs/adr/0022-health-check-contract.mdx))
- `GET /ready` — readiness; critical: `auth_grpc` (ValidateToken probe), `redis` (`PING`); advisory: `postgres` (`SELECT 1` when `POSTGRES_DSN` set), `selfhosted_llm` (`GET /models` when self-hosted enabled)
- `GET /metrics` — Prometheus text metrics

## Protected endpoints (Bearer PAT + agent header required)

All protected routes require:

- `Authorization: Bearer <pat>`
- `X-IBEX-Agent-ID: <uuid>` — must be an **active** agent owned by the token's org ([ADR-0016](../../web/content/docs/adr/0016-agent-identity-verification.mdx))

- `GET /v1/internal/auth-probe` — returns `{org_id, permissions}` for the caller token
- `GET /v1/orgs/{org_id}/auth-probe` — same; path `org_id` must be UUID; **403** if path org ≠ token org
- `POST /v1/chat/completions` — auth + agent verify + `ProxyChatCompletion`; body limit + JSON Content-Type; semantic validation; rate limit; provider routing (default `IBEX_LLM_MODE=mock` → HTTP **200** for registered models; `live` + `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `IBEX_SELFHOSTED_ENABLED` for real upstream). **501** `PROVIDER_NOT_CONFIGURED` means the **model is not in the registry**, not that forwarding is missing. Also: **429** `RATE_LIMITED`; **400** `MISSING_AGENT_ID` / `VALIDATION_ERROR` / `INVALID_JSON`; **403** `AGENT_NOT_AUTHORIZED` / `AGENT_SUSPENDED`; **413** / **415** per [ADR-0013](../../web/content/docs/adr/0013-proxy-input-validation-and-error-envelope.mdx). Mock is rejected when `IBEX_ENV=production`.

Auth validates via gRPC `ValidateToken` ([ADR-0011](../../web/content/docs/adr/0011-proxy-auth-client.mdx)). Agent ownership via gRPC `ValidateAgent` ([ADR-0016](../../web/content/docs/adr/0016-agent-identity-verification.mdx)). Parse: [ADR-0012](../../web/content/docs/adr/0012-proxy-request-normalization.mdx). Validation + envelope: [ADR-0013](../../web/content/docs/adr/0013-proxy-input-validation-and-error-envelope.mdx). Rate limit: [ADR-0015](../../web/content/docs/adr/0015-proxy-rate-limit-skeleton.mdx). Directive resolve (m2.3.2): Redis cache with Postgres fallback via `POSTGRES_DSN` (`openProxyPostgres` / `directive.PostgresStore.Load`) when Redis is also configured. Session lifecycle (m2.4.3): when `POSTGRES_DSN` is set, chat resolves/mints sticky `X-IBEX-Session-ID` (= `sessions.external_id`, not row `id`), optionally via Redis key `session:{org_id}:{agent_id}:{external_id}`, echoes that external id on stream and non-stream responses (including GetOrCreate fail-open sticky-only), and enqueues `AppendCheckpoint` on a bounded non-dropping async pool (detached Background+timeout per task, drained on shutdown). GetOrCreate failures fail open (sticky header kept; checkpoint skipped). Idle sweeper (m2.4.4): background ticker marks stale `active` sessions `abandoned` (`IBEX_SESSION_IDLE_TIMEOUT` / `IBEX_SESSION_SWEEP_INTERVAL`), invalidates Redis session keys, and uses a Postgres advisory lock across replicas. Explicit `X-IBEX-Session-End` → `completed` may be wired later; idle path uses `abandoned`. Directive injection (m2.3.3): handler applies `packages/injection.Inject` (`system_first` / `system_append` / `user_prepend`) to `provider.Request.Messages` before `Complete` ([ADR-0031](../../web/content/docs/adr/0031-system-prompt-injection.mdx)); directive content is never logged. Fail closed: token auth outage → **503** `SERVICE_DEGRADED`; agent verify outage → **503** `AUTH_UNAVAILABLE`. Rate limit Redis outage → fail open (request allowed).

## Middleware order

```text
metrics → requestContext → responseHeaders → logging → mux

POST /v1/chat/completions:
  bodyLimit → contentType → auth → agentVerify → rateLimit → directiveResolve → chatParse → providerRouting → handler (inject + Complete)

GET /v1/internal/auth-probe:
  auth → agentVerify → rateLimit → handler

GET /v1/orgs/{org_id}/auth-probe:
  pathOrgUUID → auth → agentVerify → rateLimit → handler
```

Protected responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` when rate limiting is enabled. **429** responses also include `Retry-After`.

All responses include `X-Request-ID`, `X-Trace-ID`, and `X-Response-Time` (configurable header names via env).

Request IDs use **UUID v7** when generated ([ADR-0017](../../web/content/docs/adr/0017-request-id-strategy.mdx)). Valid inbound UUIDs (v4 or v7) on `IBEX_REQUEST_ID_HEADER` are honoured; invalid values are replaced. The same ID appears in JSON error `request_id` and is propagated to auth gRPC calls via `x-request-id` metadata (`packages/reqid`).

## Configuration

See [.env.example](.env.example).

| Variable | Default | Notes |
| --- | --- | --- |
| `IBEX_PORT` | `8080` | HTTP listen port |
| `REDIS_URL` | (empty) | Required for `/ready` when set |
| `IBEX_AUTH_GRPC_ADDR` | `127.0.0.1:9091` | Auth gRPC target |
| `IBEX_AUTH_VALIDATE_TIMEOUT` | `50ms` | Per-request validate budget |
| `IBEX_AUTH_CACHE_ENABLED` | `true` | Bloom + LRU in front of ValidateToken |
| `IBEX_MAX_REQUEST_BODY_BYTES` | `1048576` | Chat body cap (1 MiB) |
| `IBEX_REQUEST_ID_HEADER` | `X-Request-ID` | Incoming/outgoing request ID |
| `IBEX_TRACE_ID_HEADER` | `X-Trace-ID` | Trace ID header |
| `IBEX_ERROR_DOCS_BASE` | (empty) | Optional `docs_url` prefix |
| `IBEX_RATE_LIMIT_DEFAULT_RPM` | `60` | Org requests per minute |
| `IBEX_RATE_LIMIT_ORG_OVERRIDES` | (empty) | `uuid=rpm,uuid2=rpm2` |
| `POSTGRES_DSN` | (empty) | Postgres for directive reads + session store/lifecycle when set |
| `IBEX_DIRECTIVE_CACHE_TTL` | `60s` | Redis TTL for directive cache keys `{org_id}:directive:{agent_id}` |
| `IBEX_SESSION_CACHE_TTL` | `60s` | Redis TTL for `session:{org_id}:{agent_id}:{external_id}` |
| `IBEX_SESSION_CHECKPOINT_WORKERS` | `8` | Async checkpoint workers |
| `IBEX_SESSION_CHECKPOINT_QUEUE` | `256` | Checkpoint queue capacity (non-dropping) |
| `IBEX_SESSION_GETORCREATE_TIMEOUT` | `50ms` | Hot-path GetOrCreate deadline (fail-open) |
| `IBEX_SESSION_IDLE_TIMEOUT` | `45m` | Idle `active` → `abandoned` threshold (`updated_at`) |
| `IBEX_SESSION_SWEEP_INTERVAL` | `1m` | Sweeper ticker interval (≤ idle timeout) |
| `IBEX_LLM_MODE` | `mock` | `mock` (in-process stub) or `live` (register configured vendors). Rejected when `IBEX_ENV=production` |
| `OPENAI_API_KEY` | (empty) | Registers OpenAI when `live` and set |
| `OPENAI_BASE_URL` | OpenAI default | Optional upstream base URL |
| `IBEX_LLM_EXTRA_MODELS` | (empty) | Comma-separated extra OpenAI model IDs (require capability overlays) |
| `ANTHROPIC_API_KEY` | (empty) | Registers Anthropic when `live` and set ([ADR-0040](../../web/content/docs/adr/0040-anthropic-provider-adapter.mdx)) |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | Anthropic API base |
| `ANTHROPIC_EXTRA_MODELS` | (empty) | Extra Claude model IDs (require capability overlays) |
| `IBEX_MODEL_CAPABILITY_OVERLAYS` | (empty) | JSON array of `ModelCapability` rows for ExtraModels / self-hosted models ([ADR-0041](../../web/content/docs/adr/0041-model-capability-registry.mdx)) |
| `IBEX_SELFHOSTED_ENABLED` | `false` | Register OpenAI-compatible self-hosted backend ([ADR-0042](../../web/content/docs/adr/0042-self-hosted-openai-compatible-adapter.mdx)) |
| `IBEX_SELFHOSTED_BASE_URL` | (empty) | Must end with `/v1` when enabled |
| `IBEX_SELFHOSTED_MODELS` | (empty) | Comma-separated model IDs (require overlays with `provider:"openai"`) |
| `IBEX_SELFHOSTED_API_KEY` | (empty) | Optional bearer; omitted when empty |
| `IBEX_PROVIDER_CIRCUIT_BREAKER_FAILURES` | `5` | Self-hosted breaker trip threshold |
| `IBEX_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | `30` | Breaker cool-down (integer seconds) |
| `IBEX_IDEMPOTENCY_TTL` | `24h` | Idempotency-Key Redis TTL (non-streaming chat) |
| `IBEX_IDEMPOTENCY_REDIS_TIMEOUT` | `50ms` | Idempotency Redis budget |
| `CLICKHOUSE_DSN` | (empty) | Optional `llm_traces` writer |
| `CLICKHOUSE_INSERT_BATCH_SIZE` | `500` | Trace insert batch size |
| `CLICKHOUSE_INSERT_FLUSH_MS` | `200` | Trace flush interval |

Full registry: [ENVIRONMENT_VARIABLES.md](../../web/engineering/ENVIRONMENT_VARIABLES.md).

## Next (Phase 2.5+) — remaining planning baseline

Anthropic adapter, model capability registry, and self-hosted OpenAI-compatible adapter are shipped
(m2.5.G1.M1–M3 / ADR-0040–0042). Still planned:

- Tokenizer counting (`IBEX_TOKENIZER_*`) keyed by `TokenizerFamily` from the capability registry
- Non-streaming response pipeline seam (`packages/responsepipeline`)
- Later: fail-open context-assembly client (`IBEX_CONTEXT_*`, Phase 3.5)

Paths and env names may change during implementation — update this README and `ENVIRONMENT_VARIABLES.md` when they land.

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
  POSTGRES_DSN=postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable \
  go run ./services/proxy/cmd/proxy
```

### Windows (PowerShell)

Replace `REPO_ROOT` with your clone path (for example `C:\dev\ibex-harness`).

Terminal 1 — auth:

```powershell
$RepoRoot = 'C:\path\to\ibex-harness'   # set to your clone
Set-Location $RepoRoot
make compose-dev-up
make db-migrate
$env:POSTGRES_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
$env:IBEX_GRPC_PORT = "9091"
go run ./services/auth/cmd/auth
```

Terminal 2 — proxy (new window; auth must stay running):

```powershell
$RepoRoot = 'C:\path\to\ibex-harness'   # set to your clone
Set-Location $RepoRoot
$env:IBEX_AUTH_GRPC_ADDR = "127.0.0.1:9091"
$env:REDIS_URL = "redis://localhost:6379/0"
$env:POSTGRES_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
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
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
# expect HTTP 200 under default IBEX_LLM_MODE=mock (registered model)
# 501 PROVIDER_NOT_CONFIGURED only if the model is not in the registry
```

Chat (PowerShell — do not use bash `\` line continuation):

```powershell
$headers = @{
  Authorization = "Bearer <pat>"
  "Content-Type" = "application/json"
  "X-IBEX-Agent-ID" = "550e8400-e29b-41d4-a716-446655440000"
}
$body = '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"hello"}]}'
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
# Phase 1 security gate (M1.5.1 — 31 SEC cases)
go test -tags=integration -run Security ./services/proxy/...
```

Security integration tests live in `proxy_security_sec*_test.go` with shared helpers in `proxy_security_helpers_test.go`. CI runs them in the required `security-integration` job.

**Windows integration tests** — default Postgres is port **5433** (`make compose-test-up`), or point at dev Postgres on **5432**:

```powershell
make compose-test-up
go test -tags=integration ./services/proxy/...

# Or reuse compose-dev-up Postgres:
$env:POSTGRES_TEST_DSN = "postgres://ibex:ibex@localhost:5432/ibex?sslmode=disable"
go test -tags=integration ./services/proxy/...
```
