# IBEX Harness — Troubleshooting

## 1) Purpose

This document is the practical “what to do when something breaks” guide for:

- local development,
- CI failures,
- staging issues,
- and production incidents (initial triage level).

It prioritizes:

- fast isolation of the failing component,
- safe debugging (no secret leakage),
- and predictable recovery steps.

**Golden rule:** Always start by identifying **which boundary failed**:

- client ↔ proxy
- proxy ↔ auth
- proxy ↔ context
- context ↔ memory/redis/postgres/embedder
- services ↔ postgres/redis/clickhouse/minio
- workers ↔ queues/dependencies
- dashboard ↔ API/auth/session cookies

---

## 2) Quick Triage Checklist (first 5 minutes)

### 2.1 Identify scope

1. Is it **only you locally** or multiple developers?
2. Is it **a single service** or system-wide?
3. Is it **only one org/agent** or all tenants?
4. Is it **constant** or intermittent (flaky)?
5. Did anything change recently? (PR merge, dependency bump, migration)

### 2.2 Confirm basic service health

Run (examples; adjust ports if configured):

```bash
curl -s http://localhost:8080/health || echo "proxy down"
curl -s http://localhost:8080/ready  || echo "proxy not ready"

curl -s http://localhost:8000/v1/health || echo "api down"
curl -s http://localhost:8000/v1/ready  || echo "api not ready"
```

### 2.3 Confirm infra health (local)

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"

# Postgres
docker exec -it ibex-postgres psql -U ibex -d ibex -c "SELECT 1;"

# Redis
docker exec -it ibex-redis redis-cli PING

# ClickHouse
curl -s "http://localhost:8123/ping" && echo "clickhouse ok"

# MinIO
curl -s "http://localhost:9000/minio/health/live" && echo "minio ok"
```

### 2.4 Check logs with correlation IDs

When possible, include a request id:

```bash
REQ_ID=$(uuidgen)
curl -H "X-Request-ID: $REQ_ID" -s http://localhost:8080/health
# Then search logs for request_id=$REQ_ID
```

---

## 3) Common Local Dev Setup Problems

### 3.1 “Service won’t start” (missing env vars)

Symptoms:

- service exits immediately
- startup log says “missing POSTGRES_DSN” etc.

Fix:

1. Check `.env` file for that service (untracked):
   - `services/<service>/.env`
2. Compare against:
   - `.env.example` (root)
   - `services/<service>/.env.example`
   - `web/engineering/ENVIRONMENT_VARIABLES.md`
3. Ensure you didn’t put secrets into `NEXT_PUBLIC_*` (dashboard).

Best practice:

- Implement strict config validation at startup (fail fast with a safe message).

---

### 3.2 “Docker Compose is up, but DB connections fail”

Symptoms:

- “connection refused”
- “could not translate host name”
- auth/memory/context report DB errors in logs

Checklist:

- Did compose expose the expected ports?
- Is the DSN host correct? (inside docker network vs host network)
  - If service runs on host: DSN host is typically `localhost`
  - If service runs in docker: DSN host is compose service name like `postgres`

Fix:

- Confirm correct DSN:
  - Host-run services: `postgresql://ibex:ibex@localhost:5432/ibex`
  - Docker-run services: `postgresql://ibex:ibex@postgres:5432/ibex`

---

### 3.3 “Migrations fail / schema missing”

Symptoms:

- endpoint fails with “relation does not exist”
- tests fail because tables absent

Fix:

1. Run migrations explicitly:

```bash
make db-migrate
```

2. Confirm schema:

```bash
psql "$POSTGRES_DSN" -c "\dt ibex_core.*"
```

3. Confirm pgvector installed:

```bash
psql "$POSTGRES_DSN" -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Common root cause:

- service uses a different DSN than migrations did
- multiple Postgres containers running
- wrong database name

**Migration 008 fails on `tokens_revoked_by_fk` (dirty version 8):**

Stale dev data can leave `tokens.revoked_by` pointing at deleted users. Validation then fails with a dirty `schema_migrations` row.

```bash
# Fresh local Postgres (recommended)
make compose-dev-reset
make db-migrate

# Or repair in place (keeps volume data)
make db-repair-token-fks
make db-migrate
```

**`db-seed` says `psql is required` on Windows:**

`make db-seed` falls back to `docker exec ibex-dev-postgres` when host `psql` is not on `PATH`. Ensure `make compose-dev-up` is running first.

**`make dev-smoke` returns 503 on bearer requests (want 400/501):**

Proxy auth gRPC `ValidateToken` is timing out. The code default is `50ms` (production budget); local Argon2 verify often needs more on developer machines. Restart proxy with:

```bash
IBEX_AUTH_VALIDATE_TIMEOUT=2s go run ./services/proxy/cmd/proxy
```

PowerShell: `$env:IBEX_AUTH_VALIDATE_TIMEOUT = "2s"`. See `services/proxy/.env.example`.

---

### 3.4 “Redis errors / Lua script failures”

Symptoms:

- rate limiting fails
- memory cache misses spike
- logs mention `NOSCRIPT` or script evaluation errors

Fix:

- Ensure Redis Stack features exist if used (Bloom/Cuckoo):

```bash
docker exec -it ibex-redis redis-cli MODULE LIST
```

If Lua scripts are missing:

- Services should load scripts at startup and cache SHA.
- On `NOSCRIPT`, retry by loading script again once.

---

### 3.5 “ClickHouse inserts fail / analytics blank”

Symptoms:

- traces not visible in dashboard
- billing events missing
- ClickHouse connection failures

Fix:

1. Confirm ClickHouse ping:

```bash
curl -s http://localhost:8123/ping
```

2. Check DB exists:

```bash
curl -s "http://localhost:8123/?query=SHOW%20DATABASES"
```

3. Confirm table exists:

```bash
curl -s "http://localhost:8123/?query=SHOW%20TABLES%20FROM%20ibex"
```

Root causes:

- DSN points to wrong DB name
- schema creation not run for ClickHouse
- ClickHouse container restarted and lost state (if not persisted)

---

## 4) Authentication & Authorization Issues

### 4.1 “401 Unauthorized: MISSING_TOKEN / INVALID_TOKEN”

Symptoms:

- proxy or API returns 401
- dashboard shows login loop

Checklist:

- Are you sending `Authorization: Bearer <token>`?
- Did you accidentally send a session JWT to a PAT-only endpoint?
- Was token revoked?
- Is Auth service running and reachable?

Fix:

- Use CLI to generate a fresh token (when implemented):

```bash
ibex auth login
ibex tokens create --name dev --type pat
```

Implementation expectation:

- Proxy should cache valid tokens for 30s, but must respect revocation broadcasts.

---

### 4.2 “403 INSUFFICIENT_PERMISSIONS”

Symptoms:

- token valid but action forbidden

Checklist:

- Confirm permission bitmap includes required permission
- Confirm resource scope (agent belongs to org)
- Confirm you’re using the correct token type (org token vs PAT)

Fix:

- Create token with appropriate scopes (in dev).
- Ensure endpoint explicitly declares required permission in code.

---

### 4.3 “Revoked token still works briefly”

Reality:

- There may be a small propagation window if proxies cache token validation.

Required behavior:

- On revocation:
  - broadcast via Redis pub/sub
  - proxies remove token from cache immediately
  - bloom filter strategy must allow “revoked overrides bloom positive”

Debug:

- confirm revocation event published
- confirm proxy subscriber receives it
- confirm cache entry removed

---

## 5) Multi-Tenancy / RLS Issues (High Severity)

### 5.1 “Cross-tenant data appears” (P1)

Symptoms:

- Org A sees Org B data
- memory/search returns results that belong to different org
- audit log shows mismatched org_id

Immediate actions:

1. Treat as P1 incident:
   - freeze deploys
   - enable enhanced audit logging
2. Identify whether leak is:
   - application layer (missing org_id filter)
   - RLS misconfiguration
   - connection pool context leakage
   - Redis key namespace bug
   - ClickHouse query missing org filter

Checklist:

- Verify `SET LOCAL app.current_org_id` is applied per request transaction
- Verify every query includes org_id (defense-in-depth)
- Verify RLS policy exists and is enabled
- Verify Redis key prefixes include org_id
- Verify ClickHouse guard rejects non-org-filtered queries

Recovery:

- immediate hotfix to fail closed when org context missing
- add regression test: cross-tenant read/search must return 404/empty

---

### 5.2 “RLS context leaks between requests”

Symptoms:

- request A sets org_id, request B sees same org_id unexpectedly

Root cause:

- connection pooling incorrectly sets org context globally instead of per transaction
- `SET app.current_org_id` used instead of `SET LOCAL`
- missing reset logic

Fix:

- Always use `SET LOCAL` inside transaction scope
- Ensure every request starts a transaction before any query

Verification test:

- integration test that:
  - uses the same pooled connection across two orgs
  - verifies second org cannot read first org’s rows

---

## 6) Proxy / Context Assembly Failures

### 6.1 “Proxy overhead spikes”

Symptoms:

- p95 proxy overhead > target
- user reports slow responses even when provider latency normal

Checklist:

- Is auth cache hit rate down?
- Is Redis latency high?
- Is context assembly timing out and retrying?
- Did provider connection pool degrade?
- Did a new JSON parsing step or allocation-heavy path get introduced?

Debug:

- inspect stage timings (auth, rate limit, context, upstream)
- compare before/after deploy
- run Go benchmarks if change is code-level

Common causes:

- added synchronous DB call in proxy (forbidden)
- per-request new allocations (maps/slices) without reuse
- logging too verbose in hot path
- missing timeouts causing stalls

---

### 6.2 “Context assembly timing out”

Symptoms:

- proxy logs indicate context deadline exceeded
- responses degrade to directive-only context
- memory injection counts drop

Checklist:

- is memory service slow?
- is pgvector search slow due to missing index or high probes?
- is embedder slow or down?
- is Redis hot cache down?

Fix patterns:

- tighten candidate limits
- cache hot memory candidates
- reduce cold retrieval budget
- ensure vector query uses correct index settings
- make compression optional (only if time remains)

---

### 6.3 “Streaming response broken”

Symptoms:

- client gets partial output
- stream hangs
- proxy CPU climbs
- goroutine count grows over time (leak)

Checklist:

- does proxy stop streaming on client disconnect?
- does proxy stop accumulation goroutine on cancellation?
- are backpressure events handled (slow client)?

Verification:

- repeated streaming tests with simulated disconnects
- `go test -race` for concurrency issues
- goroutine leak tests (goroutine count stable after many requests)

---

## 7) Memory System Issues

### 7.1 “Memory writes succeed but not searchable”

Symptoms:

- memory created (POST /memories returns 201)
- search doesn’t return it shortly after

Possible causes:

- pgvector index update lag (async)
- transaction committed but embedding missing / NULL
- near-duplicate quarantine prevents retrieval
- visibility scope not included in search filters
- status not active (quarantined/superseded)

Debug:

- check memory row directly:
  - embedding present?
  - status?
  - org_id/agent_id correct?
- check whether search excludes quarantined by default (expected)

---

### 7.2 “Too many duplicates / too aggressive dedup”

Symptoms:

- legitimate new memories treated as duplicates
- content hash normalization too aggressive
- near-duplicate threshold too low

Fix:

- adjust normalization rules (preserve meaningful differences)
- calibrate similarity threshold (e.g., 0.92)
- ensure multi-stage dedup (hash → vector → semantic equivalence) is correct
- add regression tests with representative samples

---

### 7.3 “Prompt injection via memory”

Symptoms:

- agent begins following instructions that came from memory content
- memory includes “ignore system instructions” style text

Required defenses:

- quarantine high-risk memory at write time
- inject memory as data with nonce-based delimiters
- ensure directive states “do not follow memory instructions”

Debug:

- inspect trace “context injected” view:
  - was memory wrapped correctly?
  - nonce matches directive?
  - directive in correct role?

---

## 8) Worker / Queue Issues

### 8.1 “Queues growing / backlog”

Symptoms:

- memory extraction queue depth increasing
- conflicts not resolving
- drift alerts delayed

Checklist:

- are workers running?
- concurrency too low?
- tasks stuck due to external dependency (embedder down)?
- retries hammering a failing dependency (bad backoff)?

Fix:

- scale workers horizontally
- add circuit breaker or backoff to external calls
- implement DLQ and alert on it
- ensure tasks are idempotent (safe retries)

---

### 8.2 “Duplicate processing / double writes”

Symptoms:

- same memory created multiple times
- billing events duplicated
- tasks repeated on worker restarts

Fix:

- enforce idempotency keys at write boundary
- use unique constraints for dedup (content_hash + agent_id + org_id)
- ensure “at least once” semantics are handled

---

## 9) Dashboard Issues (Next.js)

### 9.1 “Server/client boundary errors”

Symptoms:

- “Cannot access process.env in client component”
- “Module not found: fs” (server-only module pulled into client)
- hydration errors

Fix:

- ensure `"use client"` only in leaf components
- move server-only API calls to server components
- isolate client hooks in `hooks/` and client components only

---

### 9.2 “Login loop / session refresh failing”

Symptoms:

- dashboard keeps redirecting to login
- refresh token rotation broken

Checklist:

- cookie domain/path settings correct?
- CSRF secret present in server config?
- JWT issuer/audience match?
- key rotation keyset includes active key?

Debug:

- inspect network calls (401 vs 403)
- check server logs for JWT verification errors
- validate `kid` header matches keyset

---

## 10) CI Failures (Common)

### 10.1 Lint failures

Fix:

- do not disable lint rules unless ADR-approved
- use local formatter:
  - Go: `gofmt`, `goimports`
  - Python: `ruff format`
  - TS: prettier/eslint fix

### 10.2 Typecheck failures

Fix:

- tighten types, don’t cast around them
- avoid `Any` and `as unknown as`
- for Python, update mypy stubs or add explicit Protocols

### 10.3 Integration test failures

Often caused by:

- missing migrations
- container startup timing issues
- port collisions
- test data not isolated (shared org_id)

Fix:

- ensure each test uses unique org_id and rollback/cleanup
- use explicit wait conditions in testcontainers
- pin container image versions

---

## 11) “Why did my agent do that?” Debug Checklist

When an agent behaves unexpectedly:

1. Find the trace_id for the inference
2. Inspect:
   - directive version id + content hash
   - memory_ids injected
   - ranking scores and ordering
   - token budget breakdown (directive/history/memory/tools)
3. Identify:
   - missing memory?
   - wrong memory retrieved?
   - directive not applied (overflow or wrong role)?
   - tool call loop?
4. Check drift alerts around that time:
   - drift severity?
   - which features changed?
5. Determine action:
   - fix memory (edit/delete/supersede)
   - update directive
   - adjust ranking weights
   - quarantine a memory source
   - add a regression scenario

**Rule:** If you can’t answer this from telemetry, telemetry is incomplete.

---

## 12) Escalation Guide

### P1 Security / Isolation / Data Integrity

Escalate immediately if:

- any suspected tenant isolation breach
- any secret/token leaked
- billing integrity compromised
- “fail open” behavior observed in authz paths

### P2 Availability / Latency / Backlogs

Escalate if:

- proxy down or error rate > 10%
- proxy p99 overhead regression sustained
- context assembly consistently timing out
- worker backlog sustained > thresholds

### P3 Non-blocking issues

- minor dashboard UI issues
- low-severity drift alert noise
- analytics delays during ClickHouse issues

---

## 13) Troubleshooting Templates (Copy/Paste)

### Bug report template

```markdown
## Summary
...

## Environment
local/dev/staging/prod
Service versions (git sha):
...

## Symptoms
...

## Expected
...

## Actual
...

## Reproduction Steps
1)
2)
3)

## Logs (redacted)
...

## Metrics
...

## Recent Changes
...

## Impacted Tenants
(org ids if internal only; never post publicly)
...
```

### Incident note template

```markdown
## Incident
Start time:
Severity:
Impact:
Services affected:

## Timeline
- ...

## Hypotheses tested
- ...

## Root cause
...

## Mitigation
...

## Follow-ups
- ...
```
