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

## 2) RUNBOOK: Proxy High p99 Overhead — SLO Burn (page/ticket)

### Alert signals

The ratified objective is **p99 ≤ 20 ms** of proxy enforcement overhead
(`architecture-v2/05-request-lifecycle-and-slos.md`); the error budget is the 1%
of requests allowed over that boundary. Burn rate = (share of requests over
20 ms) / 0.01. Three alerts read it
(`infra/monitoring/prometheus/rules/ibex-slo.yml`):

- `IbexProxyOverheadFastBurn` — **pages.** `ibex:sli_proxy_overhead:burn_rate_1h > 14.4`
  **and** `..._5m > 14.4`, for 2m. About 2% of a 30-day budget per hour: a
  deploy-scale regression.
- `IbexProxyOverheadSlowBurn` — **ticket.** `ibex:sli_proxy_overhead:burn_rate_6h > 6`
  **and** `..._30m > 6`, for 15m. About 5% of the budget per six hours with no
  single bad window: drift that exhausts the budget in days.
- `IbexProxyOverheadSLIAbsent` — **ticket.** The SLI is unmeasurable while
  `ibex_proxy_nonstreaming_requests_total{assembly="disabled"}` advances: either
  `absent(ibex_proxy_overhead_seconds_count{assembly="disabled"})` or that series
  present but **not advancing**, for 15m. The proxy is up and answering, the
  histogram is not recording, and both burn alerts are silently inert. `absent()`
  alone catches only the missing-series case; a present-but-frozen `_count` makes
  every ratio 0/0 and stays invisible to it.

Also: customer reports “responses slower than normal”; context injection counts
drop (if timeouts occur).

### Check first (in this order)

1. **Is the SLI real before you trust it?** The histogram must exist, be
   populated on the ratified population, and advance:
   `ibex_proxy_overhead_seconds_count{assembly="disabled"}` present and moving,
   `up{job="proxy"} == 1`, and the traffic counter advancing in step. Cross-check
   the second case explicitly — does
   `ibex_proxy_nonstreaming_requests_total{assembly="disabled"}` advance while
   `_count` does not? `absent()` cannot see that one. If the SLI is missing or
   frozen, treat it as `IbexProxyOverheadSLIAbsent`, not as latency: fix
   instrumentation first.
2. **The p99 is provider-excluded by construction.** The sample is wall time
   since request start minus the provider's completion time, clamped at zero, so
   a slow provider does not raise this SLI. It is taken after the response
   pipeline ran and the body was serialized, so pipeline and serialization work
   is included; the `proxy_overhead_ms` in the response body is a pre-pipeline
   diagnostic and is deliberately smaller. The provider leg is subtracted at
   whole-ms resolution, so the sample can overstate by less than 1 ms and never
   understate. If upstream p99 is also up and this SLI is flat, the provider is
   the story — this alert is not.
3. **The population is completed non-streaming requests with
   `assembly="disabled"`.** A streaming-only regression will not move this p99,
   and neither will an `assembly="enabled"` request (it paid the Assemble RPC and
   is a different workload). “The SLO is green” does not clear streaming latency;
   check `ibex_proxy_stream_duration_seconds` separately.
4. **Confirm the profile.** The 20 ms budget is the warm mock-provider
   local/protected run with warm auth/rate-limit/directive caches and context
   assembly disabled. A cold cache, an assemble-enabled profile or a hosted runner
   is a different measurement — compare like with like before bisecting code.

### Likely causes

- Redis latency spike (auth cache / rate limits / directives)
- auth cache miss spike (auth service load increased)
- context assembly slow/timeout
- new allocation-heavy logic added to hot path
- logging turned too verbose in proxy hot path
- a change that moved the histogram off its bucket family: if `0.020` stops being
  a bucket boundary, the bad-share rules return an empty vector and the burn
  alerts go quiet while `up` stays 1 (`make slo-rules-check` asserts the boundary)

### Diagnosis (fast checklist)

1. Read the burn directly: `ibex:sli_proxy_overhead:burn_rate_1h`,
   `..._30m`, `..._6h`, and `ibex:proxy_overhead_seconds:p99_5m` / `..._p99_1h`.
2. Compare stage breakdown:
   - auth validation ms
   - rate limit ms
   - context retrieval ms (directive/hot/history/grpc)
3. Check Redis metrics:
   - latency
   - reconnects
4. Check auth cache hit rate:
   - misses rising → auth gRPC calls increasing
5. Check proxy fallbacks:
   - `context_timeout` increasing?
6. Compare to deploy version timeline:
   - did a rollout begin around onset?

### Mitigation options (safe, reversible)

- Roll back recent proxy deploy (fast) if correlated
- Scale Redis / reduce Redis latency (infra mitigation)
- Scale auth/context services if they’re bottleneck
- Temporarily tighten context deadline and force directive-only fallback if needed (feature flag / config) to protect availability

### Verification

- `ibex:sli_proxy_overhead:burn_rate_5m` and `..._1h` back under 14.4 (fast burn
  resolves); for a slow burn, `..._30m` below 6 and `..._6h` trending down
- `ibex:proxy_overhead_seconds:p99_1h` back at or under the 20 ms objective
- the histogram is still recording on the SLO population
  (`ibex_proxy_overhead_seconds_count{assembly="disabled"}` advancing, with
  `ibex_proxy_nonstreaming_requests_total{assembly="disabled"}` advancing in step)
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
- Proxy p99 overhead high (page on fast burn, ticket on slow burn / SLI absent)
- Auth failures spike (P1/P2)
- Redis down/degraded (P1/P2)
- PostgreSQL failover/unavailable (P1)
- ClickHouse down (P2)
- Worker backlog (P2)
- Tenant isolation violation (P1)
- [Re-embed the memory corpus onto a new embedding model](./re-embed.md) — procedure and prerequisites for switching the stored vector generation.

Add runbooks whenever you add a new P1/P2 alert.
