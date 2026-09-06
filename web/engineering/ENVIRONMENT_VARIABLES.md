# IBEX Harness — Environment Variables Registry

## 1) Purpose

This document is the **single source of truth** for:

- every environment variable used by IBEX Harness,
- which services use it,
- whether it is required vs optional,
- default values and safe development defaults,
- and security/rotation requirements.

**Current state:** Phases **0–2.5** are shipped; Phase **3** memory substrate is in progress. Variables marked **shipped** are wired today.
Variables marked **planned (2.5+)**, **planned (3+)**, etc. are the redesigned-roadmap planning
baseline — exact names may change during implementation when live code and an ADR say so. Keep this
file aligned with [`services/README.md`](../../services/README.md),
[`packages/README.md`](../../packages/README.md), and [`web/content/roadmap/`](../content/roadmap/).

**Rule:** If a service reads an environment variable, it must be documented here.  
**Rule:** If a variable is documented here, it must be referenced exactly (same name, same meaning) in code (once that surface ships).  
**Rule:** Do not invent production secrets in examples; use placeholders.

---

## 2) Conventions

### 2.1 Naming

- All variables are uppercase, underscore-separated.
- Prefer consistent prefixes:
  - `IBEX_...` for project-wide concerns
  - `POSTGRES_...`, `REDIS_...`, `CLICKHOUSE_...`, `S3_...` for infra
  - `JWT_...`, `OIDC_...` for auth
  - `OTEL_...` for OpenTelemetry
  - `SENTRY_...` for error tracking

### 2.2 Do not leak secrets

Secrets must never be:

- committed to git
- printed to stdout
- logged
- embedded in client bundles (dashboard)

### 2.3 Precedence (recommended)

Each service should load config in this order:

1. CLI flags (if supported)
2. Environment variables
3. `.env` file (dev only)
4. Defaults (safe defaults only)

### 2.4 “Required” means required

If a variable is marked **Required** for a service, the service must:

- fail fast at startup if missing
- print a safe error message (no secrets in logs)

---

## 3) Environment Profiles

### 3.1 Local development

- Use Docker Compose to run infra dependencies
- Use `.env` files per service (untracked)
- Use “mock mode” for LLM providers if you do not want to set keys

### 3.2 Staging

- Mirrors production topology but smaller
- Uses real TLS, real auth flows, real telemetry
- Uses controlled LLM keys (or mock mode depending on policy)

### 3.3 Production

- Uses managed secrets (Vault/Secrets Manager)
- Enforces strict security gates (mTLS optional, but recommended)
- Tight quotas and alerting enabled

---

## 4) Global Variables (All Services)

These apply across services, or are read by most services.

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `IBEX_ENV` | Yes | `development` | `development` \| `staging` \| `production` | Do not allow `production` defaults locally |
| `IBEX_SERVICE_NAME` | Yes | (none) | Name of service (e.g., `proxy`, `auth`, `memory`) | Used for logs/metrics; not secret |
| `IBEX_LOG_LEVEL` | No | `INFO` | `DEBUG` \| `INFO` \| `WARN` \| `ERROR` | `DEBUG` may expose sensitive details; never enable in prod broadly |
| `IBEX_LOG_FORMAT` | No | `json` | `json` only in production | Human-readable may be okay locally |
| `IBEX_PORT` | Yes | service-specific | Service listen port | Not secret |
| `IBEX_PUBLIC_BASE_URL` | No | (none) | Public URL for links in emails/webhooks | Ensure correct in prod |
| `IBEX_ALLOWED_ORIGINS` | No | `http://localhost:3000` | CORS allowed origins (comma-separated) | Must be strict in prod |
| `IBEX_SHUTDOWN_TIMEOUT` | No | `30s` | Graceful drain window on SIGTERM (Go duration, e.g. `30s`, `60s`) | SIGINT triggers immediate shutdown; see [ADR-0018](adr/ADR-0018-graceful-shutdown.md) |

### Tracing/Correlation

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_REQUEST_ID_HEADER` | No | `X-Request-ID` | Header name for request IDs |
| `IBEX_TRACE_ID_HEADER` | No | `X-Trace-ID` | Header name for trace IDs |

---

## 5) Database (PostgreSQL) Variables

Used by: **auth, api, memory, context, worker, dashboard (server-only)** — and any future Python/Go service that opens Postgres. Shipped today: **auth**, **proxy** (session/directive only).

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `POSTGRES_DSN` | Yes | (none) | Full DSN, e.g. `postgresql+asyncpg://user:pass@host:5432/db` | Secret (contains password) |
| `POSTGRES_MIGRATE_DSN` | No | (derived) | Go migrate runner DSN (`postgres://...` for lib/pq). If unset, `POSTGRES_DSN` is normalized (driver suffix stripped, `sslmode=disable` added when missing). | Secret |
| `POSTGRES_TEST_DSN` | No | `postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable` | Integration tests (compose test stack on port 5433) | Secret |
| `IBEX_USE_TESTCONTAINERS` | No | unset | Set to `1` to start Postgres/Redis via testcontainers instead of compose | Non-secret |
| `POSTGRES_HOST` | Optional* | `localhost` | Host if DSN not used | Prefer DSN |
| `POSTGRES_PORT` | Optional* | `5432` | Port | |
| `POSTGRES_DB` | Optional* | `ibex` | Database name | |
| `POSTGRES_USER` | Optional* | `ibex` | Username | Secret-ish |
| `POSTGRES_PASSWORD` | Optional* | (none) | Password | Secret |
| `POSTGRES_POOL_SIZE` | No | `10` | Pool size per instance | Tune per service |
| `POSTGRES_MAX_OVERFLOW` | No | `10` | Pool overflow | Prevent stampedes |
| `POSTGRES_POOL_TIMEOUT_SECONDS` | No | `10` | Acquire timeout | Avoid hung requests |
| `POSTGRES_STATEMENT_TIMEOUT_MS` | No | `5000` | DB statement timeout | Critical for reliability |
| `POSTGRES_APPLICATION_NAME` | No | `ibex-{service}` | Name shown in pg_stat_activity | Useful for ops |

\*If DSN is present, host/port/db/user/password should be ignored.

### RLS Context Settings (service internal behavior)

These are not env vars, but mandatory behavior:

- Every request must set:
  - `SET LOCAL app.current_org_id = '{org_id}'`
  - `SET LOCAL app.current_user_id = '{user_id}'` (if available)
  - `SET LOCAL app.is_service_account = 'true'` or `'false'` (string; migrations compare to `'true'`)

---

## 6) Redis Variables

**Phase 1 implemented:** `services/proxy` only (org-level rate limiting + `/ready` health check).

**Phase 2+ (documented for future services):** api, memory, context, worker.

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `REDIS_URL` | Conditional | (empty) | e.g. `redis://:password@host:6379/0` | Secret if password present; proxy: empty → Noop limiter |
| `REDIS_DB_CACHE` | No | `0` | DB index for caches | Keep consistent |
| `REDIS_DB_QUEUE` | No | `1` | DB index for queues/streams (Celery broker lists) | Keep consistent |
| `REDIS_DB_RATE_LIMIT` | No | `2` | DB index for rate limiting | Optional separation |
| `REDIS_DB_RESULTS` | No | `3` | DB index for Celery result backend keys | Short TTL; separate from broker |
| `REDIS_CONNECT_TIMEOUT_MS` | No | `200` | Connection timeout | Critical path needs low |
| `REDIS_READ_TIMEOUT_MS` | No | `200` | Read timeout | Critical path needs low |
| `REDIS_WRITE_TIMEOUT_MS` | No | `200` | Write timeout | |
| `REDIS_MAX_RETRIES` | No | `2` | Retries on transient errors | Keep small (latency) |
| `REDIS_TLS_ENABLED` | No | `false` | Enable TLS for Redis | Required in some envs |

---

## 7) ClickHouse Variables

Used by: **proxy (trace writes), api (analytics), worker (billing/analytics), dashboard (server-only analytics)**

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `CLICKHOUSE_DSN` | Yes (apps) | (none) | HTTP-oriented app DSN, e.g. `clickhouse://user:pass@host:8123/db` | Secret if password present |
| `CLICKHOUSE_MIGRATE_DSN` | No | native `localhost:9002` | golang-migrate native TCP DSN; HTTP `8123` is remapped to `9002` when used as fallback | Prefer explicit migrate DSN |
| `CLICKHOUSE_DATABASE` | No | `ibex` | DB name | |
| `CLICKHOUSE_HTTP_PORT` | No | `8123` | HTTP API port | |
| `CLICKHOUSE_NATIVE_PORT` | No | `9000` | Native protocol port (compose host map often `9002`) | |
| `CLICKHOUSE_INSERT_BATCH_SIZE` | No | `500` | Batch size for inserts | Trade latency vs throughput |
| `CLICKHOUSE_INSERT_FLUSH_MS` | No | `200` | Flush interval | Ensure bounded buffering |
| `CLICKHOUSE_QUERY_TIMEOUT_MS` | No | `5000` | Query timeout | Prevent stuck analytics |
| `CLICKHOUSE_ORG_FILTER_ENFORCEMENT` | No | `true` | Reject queries without org filter | Must remain true in prod |

**Important:** ClickHouse has no RLS. Code must enforce org filters. Schema: Phase 2 `ibex.llm_traces` ([ADR-0033](/docs/adr/0033-clickhouse-schema)); apply with `make clickhouse-migrate`.

---

## 8) Object Storage (S3/MinIO) Variables

Used by: **api, worker, dashboard (exports), session replay subsystems**

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `S3_ENDPOINT` | Yes | (none) | e.g. `http://localhost:9000` for MinIO | Use HTTPS in prod |
| `S3_REGION` | No | `us-east-1` | Region (AWS compatibility) | |
| `S3_ACCESS_KEY` | Yes | (none) | Access key | Secret |
| `S3_SECRET_KEY` | Yes | (none) | Secret key | Secret |
| `S3_BUCKET_SESSIONS` | No | `ibex-sessions` | Bucket for session archives | |
| `S3_BUCKET_EXPORTS` | No | `ibex-exports` | Bucket for exports | |
| `S3_BUCKET_BACKUPS` | No | `ibex-backups` | Bucket for backups | Secret-ish |
| `S3_USE_PATH_STYLE` | No | `true` (MinIO) | Path-style access | Needed for MinIO |
| `S3_TLS_VERIFY` | No | `true` | Verify TLS certificates | Should be true in prod |

---

## 9) Proxy Service Variables (Phase 1)

Used by: **proxy** (`services/proxy`)

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `REDIS_URL` | Conditional | (empty) | Redis for rate limiting, token-revocation SUBSCRIBE (`ibex:token:revocations`), and `/ready`. Empty → Noop limiter **and** auth cache wrap is skipped even when `IBEX_AUTH_CACHE_ENABLED=true` (WARN at startup) so revoke is immediate via gRPC. | Secret if password present |
| `IBEX_PORT` | No | `8080` | HTTP listen port | |
| `IBEX_AUTH_GRPC_ADDR` | No | `127.0.0.1:9091` | Auth gRPC target for ValidateToken | Internal; mTLS in prod |
| `IBEX_SHUTDOWN_TIMEOUT` | No | `30s` | Graceful shutdown drain | |
| `IBEX_RATE_LIMIT_DEFAULT_RPM` | No | `60` | Default org RPM | |
| `IBEX_RATE_LIMIT_ORG_OVERRIDES` | No | (empty) | `uuid=rpm` pairs | |
| `IBEX_REQUEST_ID_HEADER` | No | `X-Request-ID` | Inbound request ID header | |
| `IBEX_TRACE_ID_HEADER` | No | `X-Trace-ID` | Trace ID response header | |
| `IBEX_AUTH_VALIDATE_TIMEOUT` | No | `50ms` (code); `2s` in `services/proxy/.env.example` for local dev | Per-request auth validate budget (`ValidateToken` / `ValidateAgent`) | Code default per [ADR-0011](adr/ADR-0011-proxy-auth-client.md); use `2s` locally when Argon2 verify exceeds 50ms — see [TROUBLESHOOTING.md](TROUBLESHOOTING.md) §3.3 |
| `IBEX_AUTH_CACHE_ENABLED` | No | `true` | Request bloom + LRU wrap for ValidateToken ([ADR-0028](/docs/adr/0028-auth-cache-design)). Wrap is **skipped** (WARN) when `REDIS_URL` is empty or Redis Ping fails — revoke must not rely on LRU TTL alone without the pub/sub channel ([ADR-0029](/docs/adr/0029-token-revocation-propagation)). | Set `false` to force every request through gRPC |
| `IBEX_AUTH_CACHE_LRU_CAPACITY` | No | `5000` | Max claims entries per proxy process | |
| `IBEX_AUTH_CACHE_LRU_MAX_TTL` | No | `30s` | Max cache TTL (also max revoke lag if a pub/sub message is missed) | Requires Redis + healthy Ping for cache wrap |
| `IBEX_AUTH_CACHE_BLOOM_EXPECTED_ITEMS` | No | `10000` | Bloom sizing for invalid token hashes | |
| `IBEX_AUTH_CACHE_BLOOM_FP_RATE` | No | `0.001` | Target false-positive rate (0.1%) | |
| `IBEX_MAX_REQUEST_BODY_BYTES` | No | `1048576` | Max chat request body (1 MiB) | See [ADR-0013](adr/ADR-0013-proxy-input-validation-and-error-envelope.md) |
| `POSTGRES_DSN` | Conditional | (empty) | Postgres for directive reads and session store. When set, enables chat hot-path session lifecycle (GetOrCreate + async checkpoints). Empty → session features disabled; with Redis enables cached directive resolver | Secret; must match migrated schema |
| `IBEX_DIRECTIVE_CACHE_TTL` | No | `60s` | Redis TTL for `{org_id}:directive:{agent_id}` cache entries | Requires `POSTGRES_DSN` + `REDIS_URL` |
| `IBEX_SESSION_CACHE_TTL` | No | `60s` | Redis TTL for `session:{org_id}:{agent_id}:{external_id}` hot-path cache | Requires `REDIS_URL`; fail-open to Postgres |
| `IBEX_SESSION_CHECKPOINT_WORKERS` | No | `8` | Async checkpoint worker count (non-dropping pool) | |
| `IBEX_SESSION_CHECKPOINT_QUEUE` | No | `256` | Buffered checkpoint queue depth; full queue blocks submitter after response flush | |
| `IBEX_SESSION_GETORCREATE_TIMEOUT` | No | `50ms` | Hot-path GetOrCreate deadline; timeout fails open (omit session header, skip checkpoint) | |
| `IBEX_SESSION_IDLE_TIMEOUT` | No | `45m` | Mark `active` sessions `abandoned` when `updated_at` is older than this | Requires `POSTGRES_DSN`; proxy ticker |
| `IBEX_SESSION_SWEEP_INTERVAL` | No | `1m` | How often the idle sweeper runs; must be ≤ idle timeout | Multi-replica safe via advisory lock |
| `IBEX_IDEMPOTENCY_TTL` | No | `24h` | Redis TTL for completed `idempotency:{org_id}:{key}` chat Idempotency-Key records ([ADR-0035](/docs/adr/0035-chat-idempotency-key)). Pending claims use a separate ~9m package default. | Requires `REDIS_URL`; empty Redis → Noop (no dedupe) |
| `IBEX_IDEMPOTENCY_REDIS_TIMEOUT` | No | `50ms` | Per claim/commit Redis budget; timeout fail-opens without dedupe | Aligns with auth validate budget class |
| `IBEX_ERROR_DOCS_BASE` | No | (empty) | Base URL for `docs_url` in error envelope | Omit in dev when unset |
| `IBEX_LLM_MODE` | No | `mock` | `mock` \| `live` — `mock` registers an in-process stub; `live` registers OpenAI, Anthropic, and/or self-hosted when configured ([ADR-0026](/docs/adr/0026-openai-client-design), [ADR-0040](/docs/adr/0040-anthropic-provider-adapter), [ADR-0042](/docs/adr/0042-self-hosted-openai-compatible-adapter)). **Rejected when `IBEX_ENV=production`** | Default `mock` for CI/dev without API key; production must use `live` |
| `OPENAI_API_KEY` | Live (≥1 of OpenAI/Anthropic/self-hosted) | (none) | OpenAI API key (or OpenAI-compatible provider key) | Secret; never logged |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1` | OpenAI API base URL | Use `https://openrouter.ai/api/v1` for OpenRouter; do **not** point this at self-hosted vLLM ([ADR-0042](/docs/adr/0042-self-hosted-openai-compatible-adapter)) |
| `IBEX_LLM_EXTRA_MODELS` | No | (none) | Comma-separated extra live-mode model IDs beyond the default OpenAI allowlist | e.g. `openai/gpt-oss-20b:free` for OpenRouter; each ID needs an `IBEX_MODEL_CAPABILITY_OVERLAYS` entry |
| `OPENAI_REQUEST_TIMEOUT` | No | `120s` | Upstream request timeout | Also used as the self-hosted HTTP timeout |
| `OPENAI_MAX_RETRIES` | No | `3` | Retries on 429/5xx/network | Shared retry budget for self-hosted chat calls |
| `OPENAI_RETRY_BASE_DELAY` | No | `500ms` | Exponential backoff base | |
| `ANTHROPIC_API_KEY` | Live (≥1 of OpenAI/Anthropic/self-hosted) | (none) | Anthropic API key for Messages API adapter ([ADR-0040](/docs/adr/0040-anthropic-provider-adapter)) | Secret; never logged |
| `ANTHROPIC_BASE_URL` | No | `https://api.anthropic.com` | Anthropic API base URL | Override for gateways/proxies |
| `ANTHROPIC_REQUEST_TIMEOUT` | No | `120s` | Anthropic non-stream HTTP timeout | Stream bounded via request context |
| `ANTHROPIC_MAX_RETRIES` | No | `3` | Anthropic-specific retries (**includes HTTP 529** overloaded) | Do not copy OpenAI retry list verbatim |
| `ANTHROPIC_RETRY_BASE_DELAY` | No | `500ms` | Anthropic exponential backoff base | Cap 30s + jitter |
| `ANTHROPIC_EXTRA_MODELS` | No | (none) | Comma-separated extra Claude model IDs beyond the built-in allowlist | Each ID needs an `IBEX_MODEL_CAPABILITY_OVERLAYS` entry |
| `IBEX_MODEL_CAPABILITY_OVERLAYS` | Conditional | (none) | JSON array of capability rows for ExtraModels / self-hosted models ([ADR-0041](/docs/adr/0041-model-capability-registry)) | Required when ExtraModels or `IBEX_SELFHOSTED_MODELS` is set; fail-closed at registry build |
| `IBEX_SELFHOSTED_ENABLED` | No | `false` | Register OpenAI-compatible self-hosted backend ([ADR-0042](/docs/adr/0042-self-hosted-openai-compatible-adapter)) | Air-gapped / vLLM / TGI / Ollama path |
| `IBEX_SELFHOSTED_BASE_URL` | Conditional | (none) | Base URL ending in `/v1` for self-hosted OpenAI-compatible API | Required when enabled; private/loopback allowed only when enabled |
| `IBEX_SELFHOSTED_MODELS` | Conditional | (none) | Comma-separated model IDs served by that backend | Overlay `provider` must be `openai` (wire dialect) |
| `IBEX_SELFHOSTED_API_KEY` | No | (none) | Optional bearer for self-hosted servers that require one | Secret if set; Authorization omitted when empty |
| `IBEX_SELFHOSTED_READY_TIMEOUT` | No | `60s` | Bootstrap `GET /models` probe deadline | Fail-closed at boot |
| `IBEX_SELFHOSTED_READY_POLL` | No | `2s` | Bootstrap probe interval | |
| `IBEX_PROVIDER_CIRCUIT_BREAKER_FAILURES` | No | `5` | Consecutive Complete failures before self-hosted breaker opens | |
| `IBEX_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | No | `30` | Breaker cool-down in seconds | Integer seconds (not Go duration string) |
| `IBEX_CONTEXT_ENABLED` | No (**3.5.D.2**) | `false` | Master switch for context-assembly injection on chat completions; `false` = Phase 2 directive-only (no Assemble gRPC). Independent of empty `IBEX_CONTEXT_GRPC_TARGET` (nil client) | Additive; fail-open |
| `IBEX_CONTEXT_GRPC_TARGET` | No (**3.5.D.1**) | `127.0.0.1:9092` | Proxy dial target for ContextAssemblyService (distinct from server bind `IBEX_CONTEXT_GRPC_ADDR`) | Empty skips dial (nil client); host:port when set |
| `IBEX_CONTEXT_ASSEMBLE_TIMEOUT` | No (**3.5.D.1**) | `45ms` | Per-call AssembleContext budget on the proxy client | Independent of server `IBEX_CONTEXT_TIMEOUT` / `IBEX_CONTEXT_DEADLINE_MS` |
| `IBEX_CONTEXT_TIMEOUT` | No (**3.5.C.2**) | `45ms` | Outer parallel-retrieval deadline for context library (`ContextSettings.timeout_ms`); accepts `45` or `45ms` | Fail-open on timeout — return partial sources |
| `IBEX_CONTEXT_PACKER_DP_CELL_CEILING` | No (**3.5.C.4**) | `437570` (`70×6251`) | If `n × (buckets+1)` exceeds this, `ContextPacker` falls back to greedy ([ADR-0069](../content/docs/adr/0069-context-packer-dp-knapsack)) | Safety valve for pathological DP table sizes |
| `IBEX_CONTEXT_PACKER_MAX_CONSECUTIVE_SKIPS` | No (**3.5.C.4**) | `5` | Greedy fallback consecutive-skip limit before stopping | Used only on greedy path |
| `IBEX_CONTEXT_FORMATTER_NONCE_BYTES` | No (**3.5.C.5**) | `16` | Byte length for `secrets.token_urlsafe` **per-assembly** nonce on `<ibex_memory>` delimiters (range 1..64; [ADR-0070](../content/docs/adr/0070-context-formatter-ordering-nonce)) | One nonce per `ContextFormatter.format()` call; not a secret to log |
| `IBEX_CONTEXT_EMBED_METADATA` | No (**3.5.D.3**) | `false` | Embed top-level `ibex` JSON in non-streaming chat responses via `IBEXMetadataStage` | Off by default; no-op per request when Assemble was not attempted |
| `IBEX_EXTRACTION_REDIS_URL` | Planned **3.5** | (falls back to `REDIS_URL`) | Optional separate Redis for Celery broker | Secret if password present |
| `IBEX_TOKENIZER_MODE` | No | `local` | `local` \| `service` \| `dual` — how proxy counts tokens | **Shipped 2.5.G2.M1:** `local` only; `service`/`dual` rejected at validate |
| `IBEX_TOKENIZER_ASSET_DIR` | No | (bundled) | Optional BPE override dir (`o200k_base.tiktoken`, etc.) | Air-gapped friendly; defaults to embedded assets |
| `IBEX_TOKENIZER_SERVICE_URL` | Planned **2.5+** | (none) | Python tokenizer-service base URL | Deferred until service mode lands |
| `IBEX_DEFAULT_PROVIDER` | Planned **4** | `openai` | Org-level default when multi-provider routing is live | Phase 2/2.5 use registry registration |

**BYOK (Bring your own key) — Phase 4:**

- Org-scoped provider credentials are encrypted at rest and resolved via Auth gRPC — never returned to clients or logged. Exact env names for KMS/envelope keys belong with the auth/API surfaces when that milestone lands.

---

## 10) Auth Service Variables (Phase 1)

Used by: **auth** (`services/auth`)

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `POSTGRES_DSN` | Yes | (none) | Postgres DSN (`postgres://...`) | Secret |
| `REDIS_URL` | No | (empty) | Redis for token-revocation PUBLISH (`ibex:token:revocations`) **and** ValidateToken peer rate limiting (`ratelimit:auth:validate:*`). Empty → Noop publisher + Noop ValidateToken rate limit (private-network assumption). Proxies with empty Redis skip auth-cache wrap (immediate revoke via gRPC); do not rely on LRU TTL alone. Must match proxy Redis when auth cache is active. | Secret if password present |
| `IBEX_AUTH_VALIDATE_RPM` | No | `6000` | Per-**proxy-host** calendar-minute cap on gRPC `ValidateToken` when `REDIS_URL` is set (key = peer IP/host after stripping port). All ValidateToken calls from that host — valid and invalid — share one counter. Size to peak legitimate proxy RPS×60, not only abuse thresholds (~100 RPS at default 6000). Exceed → `RESOURCE_EXHAUSTED`. Redis check errors fail-open with WARN. | Defense-in-depth; ValidateToken remains an internal RPC |
| `IBEX_PORT` | No | `8081` | HTTP port for `/health`, `/ready`, `/metrics` | |
| `IBEX_GRPC_PORT` | No | `9091` | gRPC listen port for `AuthService` | Internal only; use mTLS in production |
| `IBEX_SHUTDOWN_TIMEOUT` | No | `30s` | Graceful shutdown drain | |
| `IBEX_ENV` | No | `development` | `development` \| `staging` \| `production` | |
| `IBEX_SERVICE_NAME` | No | `auth` | Service name for logs/telemetry | |
| `IBEX_LOG_LEVEL` | No | `INFO` | `DEBUG` \| `INFO` \| `WARN` \| `ERROR` | |

### gRPC (internal ValidateToken)

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| _(see `IBEX_GRPC_PORT` above)_ | | | | |

### Token hashing

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `IBEX_TOKEN_HASH_ALGO` | No | `argon2id` | Hash algorithm for stored tokens | Must stay argon2id |
| `IBEX_ARGON2_MEMORY_KIB` | No | `65536` | Argon2 memory | Tune for security |
| `IBEX_ARGON2_TIME` | No | `3` | Argon2 iterations | |
| `IBEX_ARGON2_PARALLELISM` | No | `4` | Argon2 parallelism | See [ADR-0010](adr/ADR-0010-cryptography-policy.md) |

### JWT signing and verification

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `JWT_ISSUER` | Yes | `ibex-harness` | Issuer claim | Must be stable |
| `JWT_AUDIENCE` | Yes | `ibex-dashboard` | Audience claim | Strict in prod |
| `JWT_ACCESS_TOKEN_TTL_SECONDS` | No | `3600` | 1 hour access tokens | Short-lived |
| `JWT_REFRESH_TOKEN_TTL_SECONDS` | No | `2592000` | 30 days | Rotate refresh tokens |
| `JWT_PRIVATE_KEY_PEM` | Yes (auth only) | (none) | RS256 signing key | Secret; only auth service |
| `JWT_PUBLIC_KEYS_PEM` | Yes (verifiers) | (none) | Keyset for verification | Public but protected |
| `JWT_KEY_ID_CURRENT` | Yes | (none) | Current key ID | Needed for rotation |
| `JWT_KEYSET_GRACE_SECONDS` | No | `3600` | Previous key grace window | Avoid token rejection |

### OIDC / Keycloak (Enterprise SSO)

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `OIDC_ENABLED` | No | `false` | Enable OIDC login | |
| `OIDC_ISSUER_URL` | Conditional | (none) | Keycloak issuer URL | Sensitive configuration |
| `OIDC_CLIENT_ID` | Conditional | (none) | OIDC client id | |
| `OIDC_CLIENT_SECRET` | Conditional | (none) | OIDC client secret | Secret |
| `OIDC_REDIRECT_URL` | Conditional | (none) | Dashboard redirect URL | Must match provider |
| `OIDC_GROUP_CLAIM` | No | `groups` | Claim name for groups | |
| `OIDC_ROLE_MAPPING_JSON` | No | (none) | JSON mapping group->role | Avoid hardcoding |

### MFA

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MFA_REQUIRED_FOR_ADMIN_ACTIONS` | No | `true` | Enforce MFA for privileged actions |
| `MFA_TOTP_WINDOW_STEPS` | No | `1` | TOTP drift window (steps) |
| `MFA_CHALLENGE_TTL_SECONDS` | No | `300` | MFA challenge validity (5 min) |

---

## 11) Context / Memory / Embedding / Tokenizer Variables

**Phase timing (planning baseline):** embedder + tokenizer → **2.5**; memory substrate → **3**;
context assembly + extraction enqueue → **3.5**; hybrid/graph retrieval knobs → **5**.

Used by: **memory**, **context**, **embedder**, **tokenizer-service** (optional), **workers**, **proxy** (clients)

### Embedding profile (deployment-time)

Profile chooses model **and** dimensionality together. Switching profiles requires a re-embed /
migration — do not mix dims in one pgvector column.

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `IBEX_EMBEDDING_PROFILE` | **Shipped 2.5.G4.M1** | `cpu` | `cpu` \| `gpu` \| `hosted` | Deployment choice, not per-request |
| `IBEX_EMBEDDING_MODEL` | No | profile-dependent | Model id (e.g. `BAAI/bge-m3`, `all-MiniLM-L6-v2`, `text-embedding-3-large`) | **Shipped 2.5.G4.M1:** validated at embedder startup |
| `IBEX_EMBEDDING_DIM` | No | profile-dependent | Vector dimensionality (e.g. `1024` for bge-m3, `384` for MiniLM) | **Shipped 2.5.G4.M1:** validated at embedder startup |
| `IBEX_EMBEDDING_API_TOKEN` | **Required at embedder startup** | (none) | Bearer token for internal `POST /v1/embed` | **Shipped 2.5.G4.M2.** Probes `/health` and `/ready` stay unauthenticated. Never logged. |
| `IBEX_EMBEDDING_TEI_BASE_URL` | **Required for `gpu` profile** | (none) | TEI sidecar base URL (HTTPS by default) | **Shipped 2.5.G4.M2.** Fail-closed: gpu without URL fails startup (service never becomes ready). Cleartext only with `TEI_ALLOW_INSECURE`. |
| `IBEX_EMBEDDING_TEI_ALLOW_INSECURE` | No | `false` | Allow cleartext TEI URLs (compose/dev only) | **Shipped 2.5.G4.M2.** Forbidden together with `TEI_API_KEY`. |
| `IBEX_EMBEDDING_TEI_API_KEY` | No | (none) | Optional Bearer token for TEI auth — **never logged** | **Shipped 2.5.G4.M2.** Some TEI deployments require this. HTTPS only. |
| `IBEX_EMBEDDING_TEI_TIMEOUT_SECONDS` | No | `30.0` | Read timeout for TEI `/embed` requests (seconds) | **Shipped 2.5.G4.M2.** |
| `IBEX_EMBEDDING_TEI_CONNECT_TIMEOUT_SECONDS` | No | `2.0` | Connect timeout for TEI requests (seconds) | **Shipped 2.5.G4.M2.** |
| `IBEX_EMBEDDING_TEI_MAX_RETRIES` | No | `2` | Max retry attempts for transient TEI errors (0 = no retries) | **Shipped 2.5.G4.M2.** Only retries 429/502/503/network errors. |
| `IBEX_EMBEDDING_TEI_HEALTH_TIMEOUT_SECONDS` | No | `30.0` | Total seconds to wait for TEI `/health` to pass on startup | **Shipped 2.5.G4.M2.** Fail-closed on timeout. |
| `IBEX_EMBEDDING_HOSTED_PROVIDER` | No | `openai` | `openai` \| `cohere` \| `voyage` | **Shipped 2.5.G4.M3.** Voyage is accepted but fail-closed (not implemented). |
| `IBEX_EMBEDDING_HOSTED_API_KEY` | **Required for `hosted` profile** | (none) | Hosted provider API key | **Shipped 2.5.G4.M3.** `SecretStr`; never logged. No stub fallback without a key. |
| `IBEX_EMBEDDING_HOSTED_BASE_URL` | No | provider default | HTTPS override of the provider base URL | **Shipped 2.5.G4.M3.** HTTPS only; userinfo in the URL is rejected. Defaults: `https://api.openai.com/v1`, `https://api.cohere.com`. |
| `IBEX_EMBEDDING_HOSTED_TIMEOUT_SECONDS` | No | `30.0` | Read timeout for hosted embed requests | **Shipped 2.5.G4.M3.** |
| `IBEX_EMBEDDING_HOSTED_CONNECT_TIMEOUT_SECONDS` | No | `2.0` | Connect timeout for hosted requests | **Shipped 2.5.G4.M3.** |
| `IBEX_EMBEDDING_HOSTED_MAX_RETRIES` | No | `2` | Max retries for transient hosted errors | **Shipped 2.5.G4.M3.** Only 429/502/503 + transport/timeout. |
| `IBEX_EMBEDDING_CACHE_ENABLED` | No | `false` | Wrap active backend with Redis content-hash cache | **Shipped 2.5.G4.M4.** Default off so cpu/stub runs without Redis. Production compose should set `true` + Redis. |
| `IBEX_EMBEDDING_CACHE_TTL_SECONDS` | No | `86400` | Redis TTL for cached float32 vectors | **Shipped 2.5.G4.M4.** Org-scoped keys `{org_id}:embed:v1:{sha256…}`. |
| `IBEX_EMBEDDING_CACHE_REDIS_URL` | No | (falls back to `REDIS_URL`) | Optional dedicated Redis URL for embedder cache | **Shipped 2.5.G4.M4.** Schemes: `redis` / `rediss` / `unix`. |
| `IBEX_EMBEDDING_CACHE_REDIS_TIMEOUT_SECONDS` | No | `0.1` | Redis connect/read/write socket timeout | **Shipped 2.5.G4.M4.** Keep short so Redis never waits like TEI/OpenAI. |
| `REDIS_URL` | Conditional | (empty) | Shared Redis URL used when cache is enabled and `IBEX_EMBEDDING_CACHE_REDIS_URL` is unset | **Shipped 2.5.G4.M4** (embedder). Cache enabled without a URL → startup not ready. |
| `OPENAI_EMBEDDING_API_KEY` | No | (none) | Optional alias for `IBEX_EMBEDDING_HOSTED_API_KEY` when provider=`openai` | **Shipped 2.5.G4.M3.** Ignored for Cohere. Prefer the canonical `IBEX_EMBEDDING_HOSTED_API_KEY`. |

Preferred starting models in the roadmap: **GPU/prod** `bge-m3` (1024-dim); **CPU/dev** MiniLM (384-dim); **hosted** OpenAI `text-embedding-3-large` (or Cohere/Voyage as alternates).

### Tokenizer

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `IBEX_TOKENIZER_MODE` | No | `local` | `local` \| `service` \| `dual` | **Shipped 2.5.G2.M1:** `local` only |
| `IBEX_TOKENIZER_SERVICE_URL` | Planned **2.5+** | (none) | Reserved for future service-mode tokenizer HTTP client | Deferred until service mode lands |
| `IBEX_TOKENIZER_TIMEOUT_MS` | Planned **2.5+** | (none) | Reserved for future service-mode count timeout | Deferred until service mode lands |
| `IBEX_TOKENIZER_ASSET_DIR` | No | (bundled) | Optional BPE override dir | Air-gapped friendly |

### Memory system knobs (Phase 3+)

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `IBEX_MEMORY_DATABASE_URL` | Conditional | (none) | Postgres DSN for memory service | Required when vector store is used (`Settings.database_url`) |
| `IBEX_MEMORY_MAX_CONTENT_CHARS` | No | `10000` | Max memory size | |
| `IBEX_MEMORY_MAX_TAGS` | No | `20` | Max tags | |
| `IBEX_MEMORY_QUARANTINE_INJECTION_THRESHOLD` | No | `0.70` | Quarantine if injection risk > threshold | Prompt-injection only — not PII |
| `IBEX_MEMORY_PII_REDACT_MIN_CONFIDENCE` | No | `0.70` | PII findings at/above score are redacted; any below → `quarantined` | ADR-0054; distinct from injection threshold |
| `IBEX_MEMORY_PII_SPACY_MODEL` | No | `en_core_web_md` | spaCy CNN model for Presidio NER | `en_core_web_trf` forbidden (Semgrep) |
| `IBEX_MEMORY_DEDUP_EXACT_ENABLED` | No | `true` | Enable content-hash exact dedup on write path (ADR-0055) | |
| `IBEX_MEMORY_NEAR_DUPLICATE_SIM_THRESHOLD` | No | `0.92` | Near-duplicate cosine floor; candidates keep `similarity >` threshold | |
| `IBEX_MEMORY_NEAR_DUPLICATE_CANDIDATE_LIMIT` | No | `10` | Max near-dup candidates from `VectorStore.search` | |
| `IBEX_MEMORY_CONFLICT_DETECTION_ENABLED` | No | `true` | Run temporal conflict stage after near-dup (ADR-0056) | |
| `IBEX_MEMORY_VECTOR_SEARCH_MIN_SIMILARITY` | No | `0.70` | Default min similarity | |
| `IBEX_MEMORY_SEARCH_FALLBACK_ENABLED` | No | `true` | Supplement sparse vector hits with GIN full-text search (m3.D.1) | Metric: `ibex_memory_search_fallback_total{triggered}` |
| `IBEX_MEMORY_HOT_CACHE_TTL_SECONDS` | No | `3600` | Cache TTL for hot memories | |
| `IBEX_HNSW_EF_SEARCH` | No | `40` | Default per-query HNSW `ef_search` | Tune from recall/latency benches; applied via `SET LOCAL` |
| `IBEX_MEMORY_EMBEDDING_BASE_URL` | No | `http://127.0.0.1:8004` | Embedder service base URL | Client: `app/clients/embedding.py` |
| `IBEX_EMBEDDING_API_TOKEN` / `IBEX_MEMORY_EMBEDDING_API_TOKEN` | Conditional | (none) | Bearer for `POST /v1/embed` | Never logged; same token space as embedder |
| `IBEX_MEMORY_EMBEDDING_TIMEOUT_SECONDS` | No | `30.0` | Embedder read timeout | |
| `IBEX_MEMORY_EMBEDDING_CONNECT_TIMEOUT_SECONDS` | No | `2.0` | Embedder connect timeout | |
| `IBEX_MEMORY_EMBEDDING_MAX_RETRIES` | No | `2` | Retries for 429/502/503 + transport | |
| `IBEX_MEMORY_HYBRID_ENABLED` | Planned **5** | `false` | Enable dense+sparse hybrid retrieval | Feature flag |
| `IBEX_MEMORY_RERANK_ENABLED` | Planned **5** | `false` | Cross-encoder rerank on fused top-K | Degrade if TEI unavailable |

### Worker service (Celery — m3.5.A.1+)

Used by: **`services/worker/`** — see [services/worker/README.md](../../services/worker/README.md).
Canonical settings use `IBEX_WORKER_*`. Legacy `CELERY_*` names in §13 are **not read** by the
worker unless explicitly aliased in a future milestone.

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `IBEX_WORKER_BROKER_URL` | Conditional | derived | Full Celery broker URL | Broker-only override |
| `IBEX_WORKER_RESULT_BACKEND` | Conditional | derived | Full Celery result-backend URL | Result-only override |
| `IBEX_EXTRACTION_REDIS_URL` | No | falls back to `REDIS_URL` | Shared Redis base for **both** derived broker and result URLs | Not broker-only |
| `IBEX_WORKER_REDIS_URL` | No | falls back to `REDIS_URL` | Alias of shared Redis base | Same derivation as `REDIS_URL` |
| `IBEX_WORKER_MAINTENANCE_BEAT_SECONDS` | No | `300` | Beat interval for maintenance noop sweep | Tunable in tests |
| `IBEX_WORKER_RESULT_EXPIRES_SECONDS` | No | `3600` | Result TTL when `ignore_result=False` | Global default ignores results |
| `IBEX_WORKER_WORKER_CONCURRENCY` | No | `4` | Worker concurrency | Compose/Makefile may override |
| `IBEX_WORKER_WORKER_HOSTNAME` | No | `ibex-worker@%h` | Celery nodename for inspect/health | `%h` = hostname |
| `IBEX_WORKER_BEAT_SCHEDULE_FILE` | No | `/var/lib/ibex/celerybeat/celerybeat-schedule` | Beat persistence path | Writable in container image |
| `IBEX_WORKER_DATABASE_URL` | Conditional | (none) | Postgres DSN for dead-letter persistence | Alias: `POSTGRES_DSN` |
| `IBEX_WORKER_METRICS_PORT` | No | `8006` | Prometheus `/metrics` HTTP port | Memory service uses `8005` |
| `IBEX_WORKER_EXTRACTION_PROVIDER` | No | `openai` | Extraction LLM backend: `openai` or `vllm` | Alias: `EXTRACTION_PROVIDER`. Fail-closed at first extract if required secrets/URL missing |
| `OPENAI_API_KEY` | Conditional | (none) | Bearer token for hosted OpenAI extraction | Required when provider=`openai`. Alias: `IBEX_WORKER_OPENAI_API_KEY` |
| `IBEX_WORKER_EXTRACTION_OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model id | |
| `IBEX_WORKER_EXTRACTION_VLLM_MODEL` | No | `Qwen2.5-14B-Instruct` | vLLM served model id | Use `Qwen2.5-7B-Instruct` if 14B VRAM is too large |
| `IBEX_WORKER_EXTRACTION_BASE_URL` | Conditional | (none) | vLLM OpenAI-compatible base URL | Required when provider=`vllm`. Aliases: `IBEX_WORKER_EXTRACTION_VLLM_BASE_URL`, `EXTRACTION_BASE_URL` |
| `IBEX_WORKER_MEMORY_BASE_URL` | Conditional | (none) | Memory service origin for `POST /v1/memories` | Alias: `MEMORY_BASE_URL` |
| `IBEX_WORKER_MEMORY_API_TOKEN` | Conditional | (none) | Bearer token with `memory:write` | Alias: `MEMORY_API_TOKEN` |
| `CLICKHOUSE_DSN` | No | (none) | HTTP DSN for `ibex.llm_traces` | Empty → skip insert (fail-open) + metric. Alias: `IBEX_WORKER_CLICKHOUSE_DSN` |
| `POSTGRES_DSN` | Conditional | (none) | Alias for worker dead-letter DSN | Required when dead-letter persistence enabled |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | (none) | OTLP gRPC collector endpoint | Same semantics as Go services (ADR-0019) |
| `OTEL_SAMPLE_RATIO` | No | `0.01` | Trace sampling ratio (0–1) | Worker reads directly (no `IBEX_WORKER_` prefix) |
| `OTEL_SERVICE_NAME` | No | `ibex-worker` | OTel resource `service.name` | Fallback when unset |
| `REDIS_URL` | No | `redis://127.0.0.1:6379/0` | Shared Redis base when worker URL unset | Dev default in `Settings` |
| `REDIS_DB_QUEUE` | No | `1` | Broker logical DB (see §6) | Celery list keys |
| `REDIS_DB_RESULTS` | No | `3` | Result backend logical DB (see §6) | `celery-task-meta-*` keys |

Production (`IBEX_ENV=production`): require `IBEX_WORKER_BROKER_URL` or one of
`REDIS_URL` / `IBEX_EXTRACTION_REDIS_URL` / `IBEX_WORKER_REDIS_URL` in the environment.

### Context assembly knobs (Phase 3.5+)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_CONTEXT_TIMEOUT` | No | `45ms` | Outer retrieval deadline (also in §9); shared by context library |
| `IBEX_CONTEXT_DIRECTIVE_TIMEOUT_MS` | No | `5` | Directive Redis GET branch budget |
| `IBEX_CONTEXT_HOT_TIMEOUT_MS` | No | `15` | Hot-memory HTTP branch budget |
| `IBEX_CONTEXT_COLD_TIMEOUT_MS` | No | `45` | Cold search HTTP branch budget (embeds server-side) |
| `IBEX_CONTEXT_PACKER_DP_CELL_CEILING` | No | `437570` | DP→greedy fallback when `n×(buckets+1)` exceeds ceiling ([ADR-0069](../content/docs/adr/0069-context-packer-dp-knapsack)) |
| `IBEX_CONTEXT_PACKER_MAX_CONSECUTIVE_SKIPS` | No | `5` | Greedy consecutive-skip stop (also in §9) |
| `IBEX_CONTEXT_FORMATTER_NONCE_BYTES` | No | `16` | `secrets.token_urlsafe` nbytes for **per-assembly** memory delimiter nonce (1..64; [ADR-0070](../content/docs/adr/0070-context-formatter-ordering-nonce)) |
| `IBEX_CONTEXT_MEMORY_BASE_URL` | Conditional | (none) | Memory service base URL for hot/cold HTTP |
| `IBEX_CONTEXT_MEMORY_API_TOKEN` | Conditional | (none) | Bearer token with `memory:read` |
| `IBEX_CONTEXT_REDIS_URL` / `REDIS_URL` | Conditional | (none) | Redis for directive cache envelope |
| `IBEX_CONTEXT_DEADLINE_MS` | No | `40` | Server-side retrieval wall for AssembleContext; effective wait `min(IBEX_CONTEXT_TIMEOUT, deadline)` ([ADR-0071](../content/docs/adr/0071-context-grpc-degradation-deadline)) |
| `IBEX_CONTEXT_GRPC_ADDR` | No | `127.0.0.1:9092` | ContextAssemblyService bind address (`python -m app`) |
| `IBEX_CONTEXT_P95_TARGET_MS` | No | `50` | Target p95 | Alerting/benchmarks |
| `IBEX_CONTEXT_MAX_MEMORIES` | No | `20` | Max memories injected |
| `IBEX_CONTEXT_RESPONSE_RESERVE_RATIO` | No | `0.15` | Reserve for model output |
| `IBEX_CONTEXT_SAFETY_BUFFER_RATIO` | No | `0.10` | Buffer to avoid overflow |

Proxy client switches for assembly live in §9 (`IBEX_CONTEXT_ENABLED`, `IBEX_CONTEXT_GRPC_TARGET`, `IBEX_CONTEXT_ASSEMBLE_TIMEOUT`, …).

### Ranking weights (defaults)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_RANK_WEIGHT_RELEVANCE` | No | `0.40` | Cosine similarity weight |
| `IBEX_RANK_WEIGHT_RECENCY` | No | `0.25` | Recency weight (category-conditional half-lives in Phase 3) |
| `IBEX_RANK_WEIGHT_USEFULNESS` | No | `0.20` | Usefulness / feedback weight |
| `IBEX_RANK_WEIGHT_CONFIDENCE` | No | `0.10` | Confidence weight |
| `IBEX_RANK_WEIGHT_FREQUENCY` | No | `0.05` | Access frequency weight |
| `IBEX_COMPOSITE_RELEVANCE_FLOOR` | No | `0.15` | Scoring-time floor on the composite relevance component; candidates below are excluded before `composite_score` ([ADR-0068](../content/docs/adr/0068-composite-relevance-gate)). Distinct from retrieval `min_similarity` ([ADR-0053](../content/docs/adr/0053-vector-store-abstraction)). Alias: `IBEX_MEMORY_COMPOSITE_RELEVANCE_FLOOR`. Must be &lt; `0.5` (settings); values &gt; `0.5` would exclude FTS hits. |

**Rule:** weights must sum to 1.0; validate at startup.

---

## 11b) MCP Memory Server Variables (2.5.G6.M1+)

Used by: **`services/mcp-memory/`** — see [MCP_SERVER.md](MCP_SERVER.md) and [ADR-0050](../content/docs/adr/0050-mcp-server-skeleton.mdx).

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `IBEX_ENV` | No | `development` | Environment name | `production` forbids stdio |
| `IBEX_MCP_TRANSPORT` | No | `streamable_http` | `streamable_http` \| `stdio` | `stdio` is dev-only |
| `IBEX_MCP_ALLOW_STDIO` | No | `false` | Explicit stdio gate | Required with `stdio` |
| `IBEX_MCP_HOST` | No | `127.0.0.1` | HTTP bind host | Containers must set `0.0.0.0` explicitly |
| `IBEX_MCP_PORT` | No | `8090` | HTTP listen port | |
| `IBEX_MCP_RESOURCE_URL` | No | `http://127.0.0.1:8090/mcp` | Public MCP resource URL | Used in auth challenge metadata; production requires non-loopback HTTPS |
| `IBEX_MCP_AUTH_SERVER_URL` | No | `http://127.0.0.1:8080` | AS URL advertised in protected-resource metadata | Discovery hook only; production requires non-loopback HTTPS |
| `IBEX_AUTH_GRPC_ADDR` | Yes (HTTP mode) | `127.0.0.1:9091` | Auth `ValidateToken` target | Insecure channel only for loopback/private IP or mesh short name (e.g. `auth`) |
| `IBEX_MCP_AUTH_TIMEOUT_MS` | No | `50` | Per-call auth deadline | Fail closed on timeout |
| `IBEX_MCP_CLICKHOUSE_URL` | No | (empty) | ClickHouse HTTP base for audit inserts (include credentials when required, e.g. `http://<user>:<password>@127.0.0.1:8123`; compose-dev fixture uses `CLICKHOUSE_PASSWORD` from `infra/compose/dev/.env`) | Empty → logging sink |
| `IBEX_MCP_AUDIT_QUEUE_SIZE` | No | `1024` | Async audit queue depth | Drops + metric when full |
| `IBEX_MCP_RATE_LIMIT_RPM` | Planned 3.5.E.4 | `120` | Independent MCP tool budget | Reserved; not enforced in G6 |
| `IBEX_MEMORY_HTTP_URL` | Conditional | (none) | Memory service base for tools | Phase 3+ |

---

## 12) Session Management Variables

Used by: **api**, **proxy**, **workers**, **dashboard**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_SESSION_HEARTBEAT_INTERVAL_SECONDS` | No | `10` | SDK heartbeat cadence |
| `IBEX_SESSION_HEARTBEAT_TTL_SECONDS` | No | `30` | Session considered dead after TTL |
| `IBEX_SESSION_SUSPEND_AFTER_SECONDS` | No | `30` | Transition to suspended after missed heartbeats |
| `IBEX_SESSION_CHECKPOINT_EVERY_N_CALLS` | No | `10` | Auto-checkpoint cadence |
| `IBEX_SESSION_CHECKPOINT_MAX_SIZE_BYTES` | No | `1048576` | 1MB max | Keep checkpoint lean |
| `IBEX_SESSION_RETENTION_DAYS` | No | `30` | Session metadata retention |
| `IBEX_SESSION_ARCHIVE_TO_S3_ENABLED` | No | `true` | Archive session transcripts |

### Loop detection

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_LOOP_WINDOW_SIZE` | No | `20` | Sliding window size |
| `IBEX_LOOP_SUSPECT_THRESHOLD` | No | `5` | Same semantic fingerprint occurrences |
| `IBEX_LOOP_STOP_THRESHOLD` | No | `10` | Hard stop threshold |
| `IBEX_LOOP_ACTION` | No | `suspend` | `warn` \| `suspend` |

---

## 13) Worker / Queue Variables (Celery)

Used by: **worker service** (preferred start: Phase **3.5** extraction; Phase **4.5** intelligence jobs)

**Shipped m3.5.A.1:** the worker reads **`IBEX_WORKER_*`** settings (§11 Worker service), not the
generic `CELERY_*` names below. Treat this table as legacy / cross-project reference until
aliases are added explicitly.

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CELERY_BROKER_URL` | Legacy | (none) | **Not read by worker** — use `IBEX_WORKER_BROKER_URL` |
| `CELERY_RESULT_BACKEND` | Legacy | (same as broker) | **Not read by worker** — use `IBEX_WORKER_RESULT_BACKEND` |
| `CELERY_RESULT_EXPIRES` | No | `3600` | Result key TTL (seconds) | Avoid unbounded Redis growth |
| `CELERY_TASK_IGNORE_RESULT` | No | `true` | Default ignore-result for extraction | Opt in per task when visibility needed |
| `CELERY_CONCURRENCY` | No | `4` | Worker processes/threads | Tune per CPU |
| `CELERY_PREFETCH_MULTIPLIER` | No | `4` | Prefetch count | Controls fairness |
| `CELERY_MAX_TASKS_PER_CHILD` | No | `1000` | Restart child to avoid leaks | |
| `CELERY_TASK_ACKS_LATE` | No | `true` | Ack only after completion | At-least-once |
| `CELERY_TASK_TIME_LIMIT_SECONDS` | No | `300` | Hard time limit | Prevent stuck jobs |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` | No | `240` | Soft limit | Graceful shutdown |
| `IBEX_CELERY_QUEUES` | Planned **3.5** | `extraction,embedding,maintenance,mcp_audit` | Queues this worker consumes | Exact names situational |

### Streams / job routing (illustrative — Celery Redis lists preferred for extraction enqueue)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_STREAM_MEMORY_EXTRACTION` | No | `memory_extraction_jobs` | Legacy/stream name if used |
| `IBEX_STREAM_CONFLICT_DETECTION` | No | `conflict_detection_jobs` | Stream name |
| `IBEX_STREAM_FINGERPRINT` | No | `fingerprint_jobs` | Phase **4.5** |
| `IBEX_STREAM_NOTIFICATIONS` | No | `notification_jobs` | Stream name |
| `IBEX_STREAM_DLQ_SUFFIX` | No | `:dlq` | Dead-letter suffix |

---

## 14) Observability Variables (OTel / Sentry)

Used by: **all services**

### OpenTelemetry

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OTEL_SERVICE_NAME` | Yes* | from `IBEX_SERVICE_NAME` | OTel service name |
| `OTEL_SERVICE_VERSION` | No | `dev` | Binary version tag |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | No | from `IBEX_ENV` | `development`, `staging`, `production` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | (none) | OTLP gRPC collector as `host:port` (e.g. `127.0.0.1:4317`); empty = noop. `http://` / `https://` prefixes are stripped (ADR-0051 local LGTM: `make observability-up`) |
| `OTEL_SAMPLE_RATIO` | No | `0.01` | Fraction of root spans sampled (`ParentBased` + `TraceIDRatio`) |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | No | `grpc` | Reserved; Phase 1 uses gRPC only |
| `OTEL_PROPAGATORS` | No | `tracecontext,baggage` | Fixed in `packages/telemetry` (ADR-0019) |

\*Required directly or via `IBEX_SERVICE_NAME` fallback.

**Sampling policy recommendation:**

- sample 1% of normal traffic
- sample 100% of errors and slow requests (implemented in app logic if needed)

### Sentry

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SENTRY_DSN` | No | (none) | DSN for error reporting |
| `SENTRY_ENVIRONMENT` | No | from `IBEX_ENV` | Environment name |
| `SENTRY_RELEASE` | No | git sha | Release version |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.01` | Trace sampling |
| `SENTRY_PROFILES_SAMPLE_RATE` | No | `0.00` | Profiles sampling (off by default) |

---

## 15) Dashboard Variables (Next.js)

Used by: **dashboard** (Phase **4** operator UI — server + client; be careful)

### Public (safe in browser)

These MUST be prefixed with `NEXT_PUBLIC_`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_BASE_URL` | Yes | `http://localhost:8000` | API server base |
| `NEXT_PUBLIC_PROXY_BASE_URL` | No | `http://localhost:8080` | Proxy base for UI tools |
| `NEXT_PUBLIC_SENTRY_DSN` | No | (none) | Public Sentry DSN (safe) |

### Server-only (must NOT be exposed to browser)

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `DASHBOARD_JWT_PUBLIC_KEYS_PEM` | Yes | (none) | Verify session JWTs | Keep server-only |
| `DASHBOARD_SESSION_COOKIE_NAME` | No | `ibex_session` | Cookie name | |
| `DASHBOARD_CSRF_SECRET` | Yes (prod) | (none) | CSRF secret | Secret |

**Rule:** never put secrets in `NEXT_PUBLIC_*`.

---

## 15.1) Local dev smoke script (`make dev-smoke`)

Used by: **`infra/scripts/smoke_local.sh`** (not read by service binaries)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_PROXY_ADDR` | No | `http://localhost:8080` | Proxy base URL for curl checks |
| `IBEX_DEV_TOKEN` | No | dev seed PAT wire value | Bearer token for smoke requests |
| `IBEX_DEV_AGENT_ID` | No | `00000000-0000-0000-0000-000000000003` | `X-IBEX-Agent-ID` header |
| `IBEX_DEV_ORG_ID` | No | `00000000-0000-0000-0000-000000000001` | Org-scoped auth-probe path |

---

## 16) Recommended `.env.example` (Top-level)

Create `/.env.example` for convenience (dev only). Do not put secrets in it.

```bash
# Environment
IBEX_ENV=development

# Core endpoints
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_PROXY_BASE_URL=http://localhost:8080

# Redis
REDIS_URL=redis://localhost:6379/0

# Postgres (example DSN; do not commit real passwords)
POSTGRES_DSN=postgresql+asyncpg://ibex:ibex@localhost:5432/ibex

# ClickHouse (HTTP; local compose maps native protocol to host port 9002 — see infra/compose/dev/README.md)
CLICKHOUSE_DSN=clickhouse://default:@localhost:8123/ibex

# MinIO
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET_SESSIONS=ibex-sessions
S3_BUCKET_EXPORTS=ibex-exports

# Observability (optional in dev)
OTEL_ENABLED=false
SENTRY_DSN=
```

---

## 16.1) Benchmark bot integration (GitHub Actions / CI)

Used by `.github/workflows/benchmark.yml` for cross-repo benchmark publishing and PR comments.

| Variable | Type | Required | Default | Description |
| --- | --- | --- | --- | --- |
| `BENCHMARK_BOT_ENABLED` | repo variable | No | unset (disabled) | When `true`, notify jobs dispatch to `ibexharness-benchmark-bot` after successful main collects (proxy + Memory HNSW + ranking-quality + write-pipeline). Extraction Quality uses a separate notify path (`extraction_benchmark_main_complete`) from `.github/workflows/extraction-eval.yml` |
| `BENCHMARK_BOT_SHA` | repo variable | Yes when PR comments enabled | — | Pinned commit SHA of `ibexharness-benchmark-bot` (no `main` fallback). Used by `.github/actions/setup-benchmark-bot` |
| `BENCHMARK_BOT_RELEASE_TAG` | repo variable | Recommended | — | Release tag for prebuilt `ibex-benchmark-bot-linux-amd64` (e.g. `bot-<7-char-sha>`). Must match `BENCHMARK_BOT_SHA` short SHA or the setup action ignores it and cargo-builds |
| `BENCHMARK_BOT_DISPATCH_TOKEN` | repo secret | Yes when `BENCHMARK_BOT_ENABLED=true` | — | Fine-grained PAT with **Contents: Read and write** on `ibexharness-benchmark-bot` (required for `repository_dispatch`) |
| `BENCHMARK_BOT_APP_ID` | repo secret | Yes when PR comments enabled | — | GitHub App ID (same as bot repo `APP_ID`; posts comments as App, not `github-actions[bot]`) |
| `BENCHMARK_BOT_APP_PRIVATE_KEY` | repo secret | Yes when PR comments enabled | — | App PEM private key |
| `BENCHMARK_BOT_INSTALLATION_ID` | repo secret | Yes when PR comments enabled | — | App installation ID on ibex-harness |

**Cadence:**

- **Every matching PR:**
  - **Benchmarks** and **Memory Benchmarks** upsert one shared sticky comment (`IBEX_BOT_COMMENT`) with Proxy, Memory HNSW, ranking-quality, and write-pipeline sections. No data PR.
  - **Extraction Quality Eval** upserts its own sticky comment via `post-extraction-pr-comment` (setup action `require-subcommand`).
- **Main / schedule collects:** notify jobs dispatch the bot; bot upserts **one** shared data PR on branch `chore/bench-data-publish` (proxy and/or memory suite JSON files in the same PR). Extraction Quality main collects dispatch `extraction_benchmark_main_complete` for the extraction-quality publish path.

**Pinning:** Keep these three in lockstep after each green bot merge:

1. Bot repo `BOT_RELEASE_SHA` = squash commit on bot `main`
2. Harness `BENCHMARK_BOT_SHA` = same SHA
3. Tag `bot-<7-char-sha>`, run bot **Release binary** (uploads binary + `.sha256`), set harness `BENCHMARK_BOT_RELEASE_TAG` to that tag, and update `.github/actions/setup-benchmark-bot/ibex-benchmark-bot-linux-amd64.sha256` to the new digest

Legacy `BENCHMARK_COMMENT_RENDERER_SHA` is deprecated — use `BENCHMARK_BOT_SHA` only. The setup action can `require-subcommand` (Memory collect jobs require `post-hnsw-pr-comment`, `post-ranking-pr-comment`, or `post-write-pr-comment`; Extraction Quality Eval requires `post-extraction-pr-comment`) so a stale release binary cannot silently break CI.

**Rotation:** Rotate `BENCHMARK_BOT_DISPATCH_TOKEN` quarterly. Rotate App private key per bot repo runbook. Update `BENCHMARK_BOT_SHA`, `BENCHMARK_BOT_RELEASE_TAG`, and bot `BOT_RELEASE_SHA` together after security-reviewed bot releases. Current pin after m3.5.B.4 bot suite: tag `bot-14bf45c` (SHA `14bf45c989c28324aad195484914a6540830c770`) with digest in `.github/actions/setup-benchmark-bot/ibex-benchmark-bot-linux-amd64.sha256`.

---

## 17) Service-Specific `.env.example` Files (Recommended)

Each service should also have its own `.env.example` in its directory, e.g.:

- `services/proxy/.env.example`
- `services/auth/.env.example`
- `services/memory/.env.example`
- etc.

Those should list only the variables actually consumed by that service.

---

## 18) Validation Requirements (Must be implemented)

Every service must validate configuration at startup:

- required vars present
- numeric values within bounds
- weights sum to 1.0 where applicable
- URLs parse correctly
- “unsafe dev defaults” rejected in production (e.g., `IBEX_ENV=production` with mock auth)

**Fail-fast** is required: better to crash at startup than to run insecurely.

---

## 19) Common Misconfigurations (and how we prevent them)

1. **Accidentally leaking secrets via Next.js**
   - Prevention: only use `NEXT_PUBLIC_*` for non-secret values
   - Add lint rule: any variable name containing `KEY|SECRET|TOKEN|PASSWORD` forbidden in client bundles

2. **Missing org filter in ClickHouse**
   - Prevention: query guard layer rejects queries missing org filter

3. **RLS context not set due to connection reuse**
   - Prevention: use `SET LOCAL` within transaction scope only
   - Add integration tests verifying cross-tenant reads return zero rows

4. **Ranking weights not summing to 1.0**
   - Prevention: validate at startup; reject misconfig

5. **Redis down disables rate limiting**
   - Prevention: local conservative limiter fallback; alert on degraded mode

---

## 20) Changing this registry

When adding, renaming, or retiring a variable:

1. Update this file in the **same PR** as the code that reads it.
2. Mark status accurately: **shipped** vs **planned (phase)** — never document fictional production knobs as required.
3. Sync `.env.example` for the affected service and any Compose notes.
4. If the change implies a new service, package, or infra dependency, update [`services/README.md`](../../services/README.md) / [`packages/README.md`](../../packages/README.md) / [`infra/README.md`](../../infra/README.md) with **evidence + ADR** (same governance as those inventories).
5. Prefer renaming over silent semantic drift (same name, different meaning).

This document is the env-var contract for IBEX Harness. Update it whenever config changes.
