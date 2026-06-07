# IBEX Harness — Environment Variables Registry

## 1) Purpose

This document is the **single source of truth** for:

- every environment variable used by IBEX Harness,
- which services use it,
- whether it is required vs optional,
- default values and safe development defaults,
- and security/rotation requirements.

**Rule:** If a service reads an environment variable, it must be documented here.  
**Rule:** If a variable is documented here, it must be referenced exactly (same name, same meaning) in code.

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

Used by: **auth, api, memory, context, worker, dashboard (server-only)**

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

Used by: **proxy, auth, api, memory, context, worker**

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `REDIS_URL` | Yes | (none) | e.g. `redis://:password@host:6379/0` | Secret if password present |
| `REDIS_DB_CACHE` | No | `0` | DB index for caches | Keep consistent |
| `REDIS_DB_QUEUE` | No | `1` | DB index for queues/streams | Keep consistent |
| `REDIS_DB_RATE_LIMIT` | No | `2` | DB index for rate limiting | Optional separation |
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
| `CLICKHOUSE_DSN` | Yes | (none) | e.g. `clickhouse://user:pass@host:8123/db` | Secret if password present |
| `CLICKHOUSE_DATABASE` | No | `ibex` | DB name | |
| `CLICKHOUSE_HTTP_PORT` | No | `8123` | HTTP API port | |
| `CLICKHOUSE_NATIVE_PORT` | No | `9000` | Native protocol port | |
| `CLICKHOUSE_INSERT_BATCH_SIZE` | No | `500` | Batch size for inserts | Trade latency vs throughput |
| `CLICKHOUSE_INSERT_FLUSH_MS` | No | `200` | Flush interval | Ensure bounded buffering |
| `CLICKHOUSE_QUERY_TIMEOUT_MS` | No | `5000` | Query timeout | Prevent stuck analytics |
| `CLICKHOUSE_ORG_FILTER_ENFORCEMENT` | No | `true` | Reject queries without org filter | Must remain true in prod |

**Important:** ClickHouse has no RLS. Code must enforce org filters.

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

## 9) LLM Provider Variables (Proxy)

Used by: **proxy**, optionally **worker** (LLM-based extraction/judging)

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `IBEX_AUTH_GRPC_ADDR` | No | `127.0.0.1:9091` | Auth gRPC target for ValidateToken | Internal; mTLS in prod |
| `IBEX_AUTH_VALIDATE_TIMEOUT` | No | `50ms` | Per-request auth validate budget | See [ADR-0011](adr/ADR-0011-proxy-auth-client.md) |
| `IBEX_MAX_REQUEST_BODY_BYTES` | No | `1048576` | Max chat request body (1 MiB) | See [ADR-0013](adr/ADR-0013-proxy-input-validation-and-error-envelope.md) |
| `IBEX_ERROR_DOCS_BASE` | No | (empty) | Base URL for `docs_url` in error envelope | Omit in dev when unset |
| `IBEX_LLM_MODE` | No | `live` | `live` \| `mock` | Mock recommended for dev |
| `OPENAI_API_KEY` | Conditional | (none) | Required if using OpenAI in `live` mode | Secret |
| `ANTHROPIC_API_KEY` | Conditional | (none) | Required if using Anthropic in `live` mode | Secret |
| `IBEX_DEFAULT_PROVIDER` | No | `openai` | Default provider | |
| `IBEX_PROVIDER_TIMEOUT_MS` | No | `60000` | Upstream provider timeout | Must be explicit |
| `IBEX_PROVIDER_CONNECT_TIMEOUT_MS` | No | `2000` | Connect timeout | |
| `IBEX_PROVIDER_MAX_RETRIES` | No | `1` | Retry on transient provider errors | Avoid double-billing |
| `IBEX_PROVIDER_CIRCUIT_BREAKER_FAILURES` | No | `5` | Failures to open circuit | Per-provider |
| `IBEX_PROVIDER_CIRCUIT_BREAKER_COOLDOWN_SECONDS` | No | `30` | Open duration | |

**BYOK (Bring your own key) variables (optional advanced):**

- If orgs store their own provider keys, those must be encrypted at rest and never returned to clients.

---

## 10) Auth Service Variables

Used by: **auth service**, **any service verifying JWTs**

### gRPC (internal ValidateToken)

| Variable | Required | Default | Description | Security Notes |
|----------|----------|---------|-------------|----------------|
| `IBEX_GRPC_PORT` | No | `9091` | gRPC listen port for `AuthService` | Internal only; use mTLS in production |

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

## 11) Context / Memory / Embedding Variables

Used by: **memory service**, **context service**, **embedder**, **workers**

### Embeddings

| Variable | Required | Default | Description | Notes |
|----------|----------|---------|-------------|-------|
| `IBEX_EMBEDDING_MODEL` | No | `all-MiniLM-L6-v2` | Embedding model name | Must match schema dim |
| `IBEX_EMBEDDING_DIM` | No | `384` | Embedding dimensionality | Must match pgvector column |
| `IBEX_EMBEDDER_URL` | Yes (if remote) | (none) | Embedder service URL | Internal |
| `IBEX_EMBEDDER_TIMEOUT_MS` | No | `2000` | Embed request timeout | Context path sensitive |
| `IBEX_EMBEDDER_BATCH_SIZE` | No | `64` | Batch size | GPU efficiency |
| `IBEX_EMBEDDER_BATCH_MAX_WAIT_MS` | No | `50` | Max wait for batching | Controls latency |

### Memory system knobs

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_MEMORY_MAX_CONTENT_CHARS` | No | `10000` | Max memory size |
| `IBEX_MEMORY_MAX_TAGS` | No | `20` | Max tags |
| `IBEX_MEMORY_QUARANTINE_INJECTION_THRESHOLD` | No | `0.70` | Quarantine if injection risk > threshold |
| `IBEX_MEMORY_DEDUP_EXACT_ENABLED` | No | `true` | Enable content-hash dedup |
| `IBEX_MEMORY_NEAR_DUPLICATE_SIM_THRESHOLD` | No | `0.92` | Near-duplicate similarity threshold |
| `IBEX_MEMORY_VECTOR_SEARCH_MIN_SIMILARITY` | No | `0.70` | Default min similarity |
| `IBEX_MEMORY_HOT_CACHE_TTL_SECONDS` | No | `3600` | Cache TTL for hot memories |

### Context assembly knobs

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_CONTEXT_DEADLINE_MS` | No | `40` | Shared deadline for context retrieval |
| `IBEX_CONTEXT_P95_TARGET_MS` | No | `50` | Target p95 | For alerting/benchmarks |
| `IBEX_CONTEXT_MAX_MEMORIES` | No | `20` | Max memories injected |
| `IBEX_CONTEXT_RESPONSE_RESERVE_RATIO` | No | `0.15` | Reserve for model output |
| `IBEX_CONTEXT_SAFETY_BUFFER_RATIO` | No | `0.10` | Buffer to avoid overflow |

### Ranking weights (defaults)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_RANK_WEIGHT_RELEVANCE` | No | `0.40` | Cosine similarity weight |
| `IBEX_RANK_WEIGHT_RECENCY` | No | `0.25` | Recency weight |
| `IBEX_RANK_WEIGHT_USEFULNESS` | No | `0.20` | Usefulness weight |
| `IBEX_RANK_WEIGHT_CONFIDENCE` | No | `0.10` | Confidence weight |
| `IBEX_RANK_WEIGHT_FREQUENCY` | No | `0.05` | Access frequency weight |

**Rule:** weights must sum to 1.0; validate at startup.

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

Used by: **worker service**

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `CELERY_BROKER_URL` | Yes | (none) | Redis broker URL | Secret if includes password |
| `CELERY_RESULT_BACKEND` | No | (same as broker) | Where results stored | |
| `CELERY_CONCURRENCY` | No | `4` | Worker processes/threads | Tune per CPU |
| `CELERY_PREFETCH_MULTIPLIER` | No | `4` | Prefetch count | Controls fairness |
| `CELERY_MAX_TASKS_PER_CHILD` | No | `1000` | Restart child to avoid leaks | |
| `CELERY_TASK_ACKS_LATE` | No | `true` | Ack only after completion | At-least-once |
| `CELERY_TASK_TIME_LIMIT_SECONDS` | No | `300` | Hard time limit | Prevent stuck jobs |
| `CELERY_TASK_SOFT_TIME_LIMIT_SECONDS` | No | `240` | Soft limit | Graceful shutdown |

### Streams / job routing (if using Redis Streams directly)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `IBEX_STREAM_MEMORY_EXTRACTION` | No | `memory_extraction_jobs` | Stream name |
| `IBEX_STREAM_CONFLICT_DETECTION` | No | `conflict_detection_jobs` | Stream name |
| `IBEX_STREAM_FINGERPRINT` | No | `fingerprint_jobs` | Stream name |
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
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | (none) | OTLP gRPC collector (e.g. `localhost:4317`); empty = noop |
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

Used by: **dashboard** (server + client, be careful)

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

This document is the env-var contract for IBEX Harness. Update it whenever config changes.
