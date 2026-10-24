# IBEX Harness — Troubleshooting Runbooks

## 0) How to Use This Document

Runbooks are step-by-step procedures for responding to alerts and incidents. They are written to be usable by:

- on-call engineers,
- new team members,
- and AI assistants supporting triage.

**Safety rules (non-negotiable):**

- Do not paste secrets into tickets or chat.
- Do not “temporarily disable auth/rate limits/RLS” to recover service.
- Prefer reversible mitigations first (scale up, rollback, circuit open, feature-flag off).
- Always capture `trace_id`, deploy version, and timeline notes.

**Incident note format (start immediately):**

```markdown
## Incident
Start time:
Severity:
Impact:
Services affected:

## Timeline
- [time] observed symptom
- [time] hypothesis + check
- [time] mitigation applied
- [time] recovery verified

## Evidence
- dashboards:
- logs:
- traces:
- versions:
```

---

## 1) RUNBOOK: Proxy Down (P1)

### Alert signals

- `up{job="proxy"} == 0` for 1m
- Error rate > 10% for 5m
- Customer reports: “LLM calls failing”

### Likely causes

- bad deploy / crash loop
- configuration missing (env vars)
- Kubernetes node issues
- dependent services unreachable causing readiness failure (auth/context)
- OOMKilled due to leak or load spike
- TLS/cert misconfiguration (ingress)

### Immediate actions (first 15 minutes)

1. Confirm blast radius:
   - is it all traffic or single region?
   - is ingress reachable?
2. Check proxy pods:
   - CrashLoopBackOff? OOMKilled? ImagePullBackOff?
3. If recent deploy occurred:
   - start rollback preparation immediately (stateless service rollback is fast)

### Diagnosis

**Kubernetes (examples):**

```bash
kubectl -n ibex-system get pods -l app=proxy
kubectl -n ibex-system describe pod <proxy-pod>
kubectl -n ibex-system logs <proxy-pod> --previous
kubectl -n ibex-system get events --sort-by=.lastTimestamp | tail -n 50
```

**If CrashLoopBackOff**

- Look at logs for:
  - “missing env var”
  - “failed to bind port”
  - “panic”
  - “cannot connect to redis/auth/context”

**If OOMKilled**

```bash
kubectl -n ibex-system top pod -l app=proxy
```

- check memory usage vs limits
- check goroutine count and allocation regressions (postmortem)

### Mitigation

1. Roll back to last known good image digest (preferred)
2. Scale proxy replicas up (if load spike)
3. If dependency is down (auth/context):
   - verify readiness logic is correct (proxy should still be live but not ready)
   - ensure readiness checks don’t hard-block liveness

### Recovery verification

- Proxy `/health` returns 200
- Proxy `/ready` returns 200 on at least N replicas
- Error rate back to baseline
- Proxy overhead latency back to baseline

### Follow-ups

- Postmortem with root cause and prevention
- Add CI gates if config mistakes caused crash
- Add memory/goroutine leak tests if OOM was leak-related

---

## 2) RUNBOOK: Proxy High p99 Overhead (P2)

### Alert signals

- p99 proxy overhead > 60ms for 10m
- customer reports: “responses slower than normal”
- context injection counts drop (if timeouts occur)

### Likely causes

- Redis latency spike (auth cache / rate limits / directives)
- auth cache miss spike (auth service load increased)
- context assembly slow/timeout
- upstream provider latency increased (note: overhead excludes provider latency, but bad measurement can blur)
- new allocation-heavy logic added to hot path
- logging turned too verbose in proxy hot path

### Diagnosis (fast checklist)

1. Compare stage breakdown:
   - auth validation ms
   - rate limit ms
   - context retrieval ms (directive/hot/history/grpc)
2. Check Redis metrics:
   - latency
   - reconnects
3. Check auth cache hit rate:
   - misses rising → auth gRPC calls increasing
4. Check proxy fallbacks:
   - `context_timeout` increasing?
5. Compare to deploy version timeline:
   - did a rollout begin around onset?

### Mitigation options (safe, reversible)

- Roll back recent proxy deploy (fast) if correlated
- Scale Redis / reduce Redis latency (infra mitigation)
- Scale auth/context services if they’re bottleneck
- Temporarily tighten context deadline and force directive-only fallback if needed (feature flag / config) to protect availability

### Verification

- p99 overhead returns to baseline (<60ms)
- p95 overhead within target (<20ms)
- fallback rate returns to baseline
- error rate stable

---

## 3) RUNBOOK: Auth Validation Failures Spike (P1/P2 depending)

### Alert signals

- spike in invalid token validations
- spike in 401 responses across proxy/api
- dashboard login failures

### Likely causes

- attack (token guessing, brute force)
- mass client misconfiguration (wrong token deployed)
- token revocation or expiration bug
- JWT key rotation misconfigured (verifiers missing new key)
- clock skew causing premature expiry validation

### Diagnosis

1. Determine which failure types:
   - invalid vs expired vs revoked vs org_suspended
2. Check if failures are concentrated to:
   - a single org (misconfigured deployment)
   - many IPs (attack)
3. If JWT failures:
   - check JWT `kid` present and matches keyset
   - check issuer/audience mismatch errors
4. Check NTP/clock:
   - if multiple services disagree on time, expiry checks fail

### Mitigation

- If attack suspected:
  - tighten rate limits on auth endpoints
  - enforce IP allowlists for enterprise orgs
  - temporarily require MFA for more operations (if supported)
- If key rotation bug:
  - restore previous keyset (keyset must include previous keys)
  - re-deploy verifiers with correct public keys
- If client misconfig:
  - notify impacted org(s)
  - allow a grace window only if safe (generally avoid)

### Verification

- 401 rates return to normal
- dashboard login works
- proxy auth cache hit rate stable

---

## 4) RUNBOOK: Redis Down / Redis Degraded (P1/P2)

### Alert signals

- redis exporter down
- proxy fallbacks `redis_down` > 0
- rate limiting becomes conservative (possible false throttling)
- session heartbeats missing → sessions suspend unexpectedly

### Likely causes

- Redis node failure / failover
- network partition
- memory pressure / eviction storm
- slow disk (AOF fsync stalls)
- cluster resharding / misconfig

### Diagnosis

1. Is Redis fully down or just slow?
2. Check:
   - latency percentile
   - memory usage / evictions
   - replication lag (if HA)
3. Determine impact:
   - proxy uses local fallback for rate limits? (should)
   - session heartbeats impacted? (likely)
   - memory cache misses spike? (expected)

### Mitigation

- If HA present: ensure failover completed
- Scale Redis / move to larger instance
- Reduce load:
  - temporarily reduce caching writes (if safe)
  - increase TTLs cautiously (avoid stampede)
- In extreme cases:
  - proxy uses conservative local limiter (already designed)
  - disable non-critical Redis features temporarily (analytics buffers, pubsub usage)

### Verification

- Redis latency back to baseline
- proxy fallbacks stop increasing
- session suspensions return to normal

---

## 5) RUNBOOK: PostgreSQL Failover / DB Unavailable (P1)

### Alert signals

- API/memory/context errors increase (DB failures)
- 503s from services that require DB
- Patroni failover event (if used)

### Likely causes

- primary node failure
- storage saturation
- connection exhaustion
- long-running queries / locks
- migration locking table accidentally

### Diagnosis

1. Check DB connectivity from services
2. Check connection pool saturation:
   - are pools exhausted causing request timeouts?
3. Check for locks:
   - `pg_stat_activity`, `pg_locks`
4. Confirm failover status if HA:
   - who is primary now?
   - are apps reconnecting?

### Mitigation

- If failover in progress: hold steady; ensure services retry with backoff
- If connection exhaustion:
  - reduce max pool sizes
  - ensure PgBouncer configured (transaction pooling)
- If lock issue caused by migration:
  - stop migration
  - kill offending query if safe
  - roll forward with safer migration path

### Verification

- DB reachable
- error rates drop
- queue backlogs not exploding

---

## 6) RUNBOOK: ClickHouse Down / Analytics Missing (P2)

### Alert signals

- traces not visible in dashboard
- billing events ingestion lag increasing
- clickhouse exporter down

### Likely causes

- clickhouse node failure
- disk full
- large merge backlog
- schema mismatch after deploy

### Diagnosis

1. Determine whether ingestion is failing or only querying failing
2. Check buffers:
   - proxy should buffer trace writes (Redis or disk spill)
   - billing events must not be dropped

### Mitigation

- restore clickhouse availability (infra team)
- ensure buffered events replay with rate limiting (avoid overload after recovery)
- if disk full: increase storage or drop old partitions (if retention policy allows)

### Verification

- ingestion resumed
- replay backlog decreasing
- dashboards show fresh data

---

## 7) RUNBOOK: Worker Backlog (P2)

### Alert signals

- queue depth > 10k for >10m
- DLQ increasing
- delayed drift alerts, delayed extraction

### Likely causes

- embedder down / slow
- memory service slow
- insufficient worker replicas
- tasks retrying too aggressively

### Diagnosis

- check which queue is backed up:
  - memory_extraction_jobs
  - conflict_detection_jobs
  - fingerprint_jobs
- check failure reasons in worker logs
- check dependency status (embedder, DB)

### Mitigation

- scale workers horizontally (fast)
- reduce retry aggressiveness (if storm)
- open circuit for failing dependency calls (if implemented)
- temporarily disable non-critical jobs (fingerprinting) to preserve extraction SLA (feature flags)

### Verification

- queue depth trending down
- DLQ stable or decreasing
- task failure rate returns to baseline

---

## 8) RUNBOOK: Suspected Tenant Isolation Violation (P1)

### Alert signals

- any telemetry indicates cross-tenant access
- user report: seeing another org’s data
- audit log anomaly detected

### Immediate actions (do not delay)

1. Declare P1 incident
2. Freeze deployments
3. Enable enhanced audit logging (safe mode)
4. Identify suspected path:
   - API endpoint?
   - Redis key namespace?
   - ClickHouse query?
   - connection pool org context leak?

### Diagnosis plan (priority order)

1. Confirm if it is real:
   - reproduce with controlled test orgs if possible
2. Check DB RLS:
   - are policies enabled?
   - does `current_setting('app.current_org_id')` set properly?
3. Check code path:
   - any query missing org_id filter?
4. Check Redis:
   - keys not namespaced?
   - shared key collision?
5. Check ClickHouse:
   - query lacking org filter?
   - guard missing?

### Mitigation

- Fail closed if org context missing or mismatched
- Hotfix query guards and key namespacing
- If in doubt: disable affected endpoints temporarily (feature flag) while preserving core traffic

### Verification

- cross-tenant tests pass in staging
- reproduction no longer possible
- incident review + regression tests committed

---

## 9) Runbook Index (Maintain this)

- Proxy Down (P1)
- Proxy p99 overhead high (P2)
- Auth failures spike (P1/P2)
- Redis down/degraded (P1/P2)
- PostgreSQL failover/unavailable (P1)
- ClickHouse down (P2)
- Worker backlog (P2)
- Tenant isolation violation (P1)

Add runbooks whenever you add a new P1/P2 alert.
