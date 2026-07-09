# IBEX Harness — Monitoring & Observability

## 1) Purpose

IBEX Harness is a distributed system with:

- a latency-critical proxy path,
- async background processing,
- strict tenant isolation requirements,
- and cost/billing correctness constraints.

This document defines the **complete observability strategy**:

- what we measure (metrics),
- what we log (structured logs),
- how we trace (distributed tracing),
- how we alert (SLO-driven alerts),
- and how we debug “why did my agent do that?” issues.

Observability is a feature. If it is missing, the system is not production-ready.

---

## 2) Core Principles

### O1 — Every production incident should be diagnosable from telemetry

For any incident (latency spike, error spike, memory regression, auth failures), we must answer:

- What broke?
- When did it start?
- Which orgs/agents are impacted?
- Is it a dependency issue (Redis/Postgres/ClickHouse/provider)?
- What changed recently?
- What is the mitigation?

### O2 — Cardinality is a budget

Metrics with high-cardinality labels can melt Prometheus.
We measure what’s useful without exploding label space.

### O3 — Link everything via trace_id

- Every request must have `trace_id` and `request_id`.
- Logs must include `trace_id`.
- Traces must propagate across service boundaries (HTTP/gRPC/queues).

### O4 — SLOs drive alerting, not “CPU is high”

Alert on symptoms that matter to users:

- proxy p99 overhead,
- context assembly p95 latency,
- error rate,
- memory retrieval hit rate,
- queue backlog,
- billing pipeline integrity.

### O5 — Privacy by default

Do not store raw memory content in logs.
Do not store raw prompts/responses in logs by default.
Debug views can show content only with:

- explicit user permission,
- redaction pipeline,
- and audit logging.

---

## 3) Observability Stack

### Metrics

- **Prometheus**: collection + alert evaluation
- **Grafana**: dashboards + alert routing (optional)
- **Exporters**:
  - app-native Prometheus metrics endpoints (`/metrics`)
  - node exporter / kube-state-metrics in Kubernetes
  - postgres exporter, redis exporter, clickhouse exporter

### Logs

- Structured JSON logs to stdout
- Aggregation via:
  - **Loki** (preferred) or ELK
- Queries via Grafana Explore

### Traces

- **OpenTelemetry SDKs** in all services
- Export to **Tempo** or **Jaeger**
- Sampling:
  - 100% for errors and slow requests
  - low % for normal traffic

### Error Tracking

- **Sentry** for app-level errors with grouping
- Link Sentry events to trace_id/request_id

---

## 4) Identifiers and Correlation

### Required IDs

- `request_id`: unique per inbound request (UUID)
- `trace_id`: distributed trace identifier (W3C TraceContext)
- `org_id`: tenant identifier (UUID)
- `agent_id`: agent identifier (UUID when relevant)
- `session_id`: session identifier (UUID v7 preferred)

### Propagation rules

- HTTP: use `traceparent` header (W3C) + `X-Request-ID`
- gRPC: OTel propagation via metadata
- Queues/Streams: include trace context in message payload:
  - `trace_id`, `span_id` (optional), `request_id`

**Never** use user email or memory content as an identifier.

---

## 5) Metric Naming Conventions

### Format

```text
ibex_<service>_<metric_name>_<unit>
```

Examples:

- `ibex_proxy_request_duration_seconds`
- `ibex_context_assembly_duration_seconds`
- `ibex_memory_search_duration_seconds`
- `ibex_auth_token_validation_total`
- `ibex_worker_queue_depth`

### Metric Types

- Counters: `_total`
- Gauges: `_current` or no suffix
- Histograms: `_duration_seconds`, `_size_bytes`

### Label rules (cardinality discipline)

Allowed low-cardinality labels:

- `service` (static per service)
- `operation` (bounded enum)
- `status` (`success|error|timeout|degraded`)
- `provider` (`openai|anthropic|...`)
- `http_method`, `route` (route template, not raw path)
- `error_code` (bounded enum)
- `tier` (`free|pro|enterprise`)

Forbidden high-cardinality labels (do NOT use in metrics):

- `org_id`
- `agent_id`
- `session_id`
- `memory_id`
- `user_id`
- `request_id`
- `trace_id`
- raw URL paths
- raw exception messages

**Rule:** tenant-level breakdown belongs in ClickHouse analytics, not Prometheus.

---

## 6) Golden Signals (Required per service)

Every service must publish these metrics:

### 6.1 Traffic

- requests per second
- request counts by status

### 6.2 Errors

- error rate by class (4xx vs 5xx)
- known error_code counts

### 6.3 Latency

- histogram (p50/p95/p99)
- breakdown of critical stages (where relevant)

### 6.4 Saturation

- CPU/memory (via Kubernetes metrics)
- DB pool usage
- queue depth (workers)
- connection counts (proxy)

---

## 7) Service-Specific Metrics (Spec)

### 7.1 Proxy Service (Go) — latency-critical

#### Core request metrics

- `ibex_proxy_requests_total{operation,status}`
- `ibex_proxy_request_duration_seconds_bucket{operation,status}`
- `ibex_proxy_active_connections_current`
- `ibex_proxy_inflight_requests_current`

#### Stage breakdown (histograms)

- `ibex_proxy_auth_duration_seconds_bucket{status}`
- `ibex_proxy_rate_limit_duration_seconds_bucket{status}`
- `ibex_proxy_context_fetch_duration_seconds_bucket{stage,status}`
  - stages: `directive|hot_memories|history|context_grpc`
- `ibex_proxy_upstream_duration_seconds_bucket{provider,status}`
- `ibex_proxy_stream_duration_seconds_bucket{provider,status}`
- `ibex_proxy_overhead_duration_seconds_bucket{status}`

#### Cache and fallback behavior

- `ibex_proxy_auth_cache_hits_total`
- `ibex_proxy_auth_cache_misses_total`
- `ibex_proxy_auth_bloom_negatives_total`
- `ibex_proxy_fallbacks_total{reason}`
  - reasons: `context_timeout|redis_down|auth_down|memory_timeout|provider_circuit_open`
- `ibex_proxy_circuit_breaker_state_current{provider,state}`
  - state: `closed|open|half_open`

#### Rate limiting

- `ibex_proxy_rate_limited_total{level}`
  - level: `agent|org|global|quota_monthly`
- `ibex_proxy_quota_exceeded_total{quota_type}`
  - quota_type: `monthly_tokens|memory_quota|requests_daily`

#### Streaming correctness

- `ibex_proxy_stream_client_disconnects_total`
- `ibex_proxy_stream_upstream_disconnects_total`
- `ibex_proxy_stream_backpressure_events_total`

### 7.2 Auth Service (Go)

- `ibex_auth_token_validations_total{result}`
  - result: `valid|invalid|expired|revoked|org_suspended`
- `ibex_auth_token_validation_duration_seconds_bucket{result}`
- `ibex_auth_jwt_issued_total{type}`
  - type: `access|refresh`
- `ibex_auth_jwt_verification_failures_total{reason}`
  - reason: `bad_signature|expired|aud_mismatch|iss_mismatch|unknown_kid`
- `ibex_auth_key_rotation_events_total{result}`
- `ibex_auth_mfa_challenges_total{result}`
  - result: `verified|failed|expired`
- `ibex_auth_revocations_total{type}`
  - type: `pat|org_token|service_token`

### 7.3 Memory Service (Python)

- `ibex_memory_write_total{status}`
- `ibex_memory_write_duration_seconds_bucket{status}`
- `ibex_memory_search_total{status}`
- `ibex_memory_search_duration_seconds_bucket{status}`
- `ibex_memory_dedup_total{result}`
  - result: `exact_duplicate|near_duplicate|novel`
- `ibex_memory_conflicts_total{type}`
  - type: `contradiction|overlap|supersedes|specializes`
- `ibex_memory_quarantined_total{reason}`
  - reason: `pii|injection_risk`
- `ibex_memory_cache_hits_total`
- `ibex_memory_cache_misses_total`
- `ibex_memory_vector_query_candidates_current` (gauge / summary)
- `ibex_memory_pgvector_index_lag_seconds` (if async indexing lag tracked)

### 7.4 Context Assembly (Python gRPC)

- `ibex_context_assembly_total{status}`
- `ibex_context_assembly_duration_seconds_bucket{status}`
- `ibex_context_deadline_exceeded_total`
- `ibex_context_budget_utilization_ratio` (histogram)
- `ibex_context_memories_included_count` (histogram)
- `ibex_context_candidates_evaluated_count` (histogram)
- `ibex_context_compression_invocations_total`
- `ibex_context_retrieval_failures_total{stage}`
  - stage: `directive|hot|cold|history`

### 7.5 Embedder (Python)

- `ibex_embed_requests_total{status}`
- `ibex_embed_duration_seconds_bucket{status}`
- `ibex_embed_batch_size` (histogram)
- `ibex_embed_batch_flush_reason_total{reason}`
  - reason: `size_threshold|time_threshold`
- `ibex_embed_model_load_failures_total`
- `ibex_embed_input_truncated_total` (if truncation exists)

### 7.6 Workers (Celery)

- `ibex_worker_tasks_total{task_name,status}`
- `ibex_worker_task_duration_seconds_bucket{task_name,status}`
- `ibex_worker_retries_total{task_name}`
- `ibex_worker_dlq_total{task_name}`
- `ibex_worker_queue_depth_current{queue_name}`
- `ibex_worker_idempotency_replays_total{task_name}`

### 7.7 API Server (Python management plane)

- `ibex_api_requests_total{route,status}`
- `ibex_api_request_duration_seconds_bucket{route,status}`
- `ibex_api_db_query_duration_seconds_bucket{query_type}`
- `ibex_api_db_pool_in_use_current`
- `ibex_api_cache_hit_total{cache}`
- `ibex_api_cache_miss_total{cache}`

### 7.8 Dashboard (Next.js)

Client metrics are optional, but recommended via RUM:

- `ibex_dashboard_page_load_seconds` (p50/p95)
- `ibex_dashboard_api_error_total{code}`
- `ibex_dashboard_js_error_total` (Sentry already covers)

---

## 8) Logging Specification (Structured JSON)

### Required fields

All logs must include:

- `timestamp` (ISO8601)
- `level` (`DEBUG|INFO|WARN|ERROR`)
- `service`
- `message`
- `trace_id` (if in request context)
- `request_id` (if in request context)

When available, include:

- `org_id`, `agent_id`, `session_id` (IDs only)
- `operation`
- `duration_ms`
- `status`
- `error_code` (bounded enum)

### Forbidden fields

Never log:

- token values / API keys / secrets
- raw memory content by default
- full prompts or completions by default
- passwords, MFA codes, JWT payloads

### PII and content logging policy

If you need to log content for debugging:

- require explicit `IBEX_LOG_SENSITIVE=true` AND `IBEX_ENV=development`
- redact known PII patterns
- truncate content to a safe max length
- add audit log entry when sensitive logging enabled (staging/prod)

### Example log lines

Proxy request success:

```json
{
  "timestamp": "2026-05-30T12:00:01.123Z",
  "level": "INFO",
  "service": "proxy",
  "message": "proxied inference request",
  "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
  "request_id": "a1b2c3d4-e5f6-...",
  "org_id": "123e4567-e89b-...",
  "agent_id": "550e8400-e29b-...",
  "session_id": "7c9e6679-7425-...",
  "provider": "openai",
  "model": "gpt-4-turbo",
  "memories_injected": 5,
  "context_assembly_ms": 42,
  "proxy_overhead_ms": 16,
  "status": "success"
}
```

Auth failure (no token):

```json
{
  "timestamp": "2026-05-30T12:00:02.456Z",
  "level": "WARN",
  "service": "proxy",
  "message": "authentication failed",
  "trace_id": "....",
  "request_id": "....",
  "status": "auth_failed",
  "error_code": "MISSING_TOKEN"
}
```

Redis degraded fallback:

```json
{
  "timestamp": "2026-05-30T12:00:03.000Z",
  "level": "WARN",
  "service": "proxy",
  "message": "redis unavailable; using local conservative rate limiter",
  "trace_id": "....",
  "request_id": "....",
  "status": "degraded",
  "fallback_reason": "redis_down"
}
```

---

## 9) Tracing Specification (OpenTelemetry)

### 9.1 Span naming

Use consistent names:

- `proxy.request`
- `proxy.auth.validate`
- `proxy.ratelimit.check`
- `proxy.context.directive`
- `proxy.context.hot_memories`
- `proxy.context.history`
- `proxy.context.grpc`
- `proxy.upstream.call`
- `proxy.stream.forward`
- `context.assemble`
- `memory.search`
- `memory.write`
- `auth.validate_token`

### 9.2 Span attributes (low cardinality)

Allowed attributes:

- `service.name`
- `http.method`, `http.route`, `http.status_code`
- `rpc.service`, `rpc.method`
- `provider`, `model`
- `status` (`success|error|timeout|degraded`)
- `error_code` (bounded enum)

Avoid attributes:

- org_id, agent_id, session_id in span attributes (high cardinality)

Instead:

- log them in structured logs
- store tenant breakdown in ClickHouse analytics

### 9.3 Sampling

Default: 1% normal requests.

Always sample:

- errors
- requests above “slow” threshold:
  - proxy total > 500ms
  - context assembly > 100ms
  - memory search > 200ms

Implementation approach:

- tail-based sampling in Tempo/Collector if available, OR
- head-based sampling in SDK + “force sample on error” logic where possible.

### 9.4 Async boundaries

When publishing a job to a queue/stream:

- include `traceparent` and `tracestate` in message metadata
- worker extracts and continues trace

---

## 10) Dashboards (Grafana)

### 10.1 Dashboard: “System Overview”

Panels:

- RPS by service
- Error rate by service (5xx and 4xx separately)
- p95/p99 latency for proxy and context
- Redis health (latency, errors)
- Postgres health (connections, slow queries)
- Queue depth (workers)
- Provider availability (circuit breaker open counts)
- SLO burn rate (see SLO section)

### 10.2 Dashboard: “Proxy — Critical Path”

Panels:

- proxy overhead p50/p95/p99
- auth validation latency p95
- rate limit check latency p95
- context assembly latency p95
- upstream provider latency p95/p99
- fallbacks by reason
- circuit breaker state counts
- active connections / inflight requests
- stream disconnect events

### 10.3 Dashboard: “Memory System”

Panels:

- memory write rate + latency
- memory search rate + latency
- dedup outcomes (exact/near/novel)
- quarantined memories rate
- conflict resolutions rate by type
- cache hit rate
- pgvector query candidates (distribution)

### 10.4 Dashboard: “Workers”

Panels:

- tasks processed/sec by task_name
- retry rate by task_name
- DLQ depth by task_name
- queue depth by queue_name
- task duration p95 by task_name

### 10.5 Dashboard: “Billing Integrity”

Panels:

- billing events ingestion rate
- billing pipeline lag (event time vs processed time)
- reconciliation errors count
- usage counters vs billing events delta

---

## 11) Alerts (Prometheus Rules)

### 11.1 Alert severity

- **P1**: page immediately (user impact / security / data loss risk)
- **P2**: urgent, page if persistent
- **P3**: ticket + investigate in business hours

### 11.2 P1 Alerts (examples)

**Proxy is down or rejecting traffic**

- Condition: `up{job="proxy"} == 0` for 1m
- Condition: `rate(ibex_proxy_requests_total{status="error"}[5m]) / rate(ibex_proxy_requests_total[5m]) > 0.10` for 5m

**Tenant isolation suspicion**

- Condition: any log/metric event `tenant_isolation_violation_total > 0`
- This should be “never happens”; immediate incident.

**Auth failures spike**

- Condition: `rate(ibex_auth_token_validations_total{result="invalid"}[5m])` sudden jump AND overall traffic stable
- Often indicates token leak/attack or breaking client update.

**Billing pipeline broken**

- Condition: billing ingest rate drops to near zero while proxy traffic exists
- Condition: billing pipeline lag > threshold for sustained time

### 11.3 P2 Alerts (examples)

**Proxy p99 overhead regression**

- Condition: `histogram_quantile(0.99, rate(ibex_proxy_overhead_duration_seconds_bucket[5m])) > 0.06` for 10m

**Context assembly p95 too slow**

- Condition: `histogram_quantile(0.95, rate(ibex_context_assembly_duration_seconds_bucket[5m])) > 0.05` for 10m

**Redis degraded**

- Condition: `rate(ibex_proxy_fallbacks_total{reason="redis_down"}[5m]) > 0` for 5m
- Condition: redis exporter shows high latency or frequent reconnects

**Worker backlog**

- Condition: `ibex_worker_queue_depth_current{queue_name="memory_extraction"} > 10000` for 10m

### 11.4 Example Prometheus rule snippets

```yaml
groups:
  - name: ibex-proxy
    rules:
      - alert: IbexProxyDown
        expr: up{job="proxy"} == 0
        for: 1m
        labels:
          severity: P1
        annotations:
          summary: "Proxy is down"
          description: "No proxy instances are up for >1m."

      - alert: IbexProxyHighP99Overhead
        expr: |
          histogram_quantile(0.99,
            rate(ibex_proxy_overhead_duration_seconds_bucket[5m])
          ) > 0.06
        for: 10m
        labels:
          severity: P2
        annotations:
          summary: "Proxy p99 overhead too high"
          description: "p99 proxy overhead > 60ms for 10m."

  - name: ibex-context
    rules:
      - alert: IbexContextAssemblySlow
        expr: |
          histogram_quantile(0.95,
            rate(ibex_context_assembly_duration_seconds_bucket[5m])
          ) > 0.05
        for: 10m
        labels:
          severity: P2
        annotations:
          summary: "Context assembly p95 too slow"
          description: "p95 context assembly > 50ms for 10m."

  - name: ibex-workers
    rules:
      - alert: IbexWorkerBacklogMemoryExtraction
        expr: ibex_worker_queue_depth_current{queue_name="memory_extraction"} > 10000
        for: 10m
        labels:
          severity: P2
        annotations:
          summary: "Memory extraction backlog growing"
          description: "Queue depth > 10k for 10m."
```

---

## 12) SLOs / SLIs (What We Guarantee)

### 12.1 Proxy Availability SLO

- SLI: successful proxy requests / total proxy requests
- SLO: 99.9% monthly

### 12.2 Proxy Overhead Latency SLO

- SLI: `proxy_overhead_ms` p99
- SLO: p99 < 60ms, p95 < 20ms (excluding provider latency)

### 12.3 Memory Search Latency SLO

- SLI: memory search p95
- SLO: p95 < 100ms (for typical dataset sizes)

### 12.4 Auth Validation SLO

- SLI: auth validation p95 (cache hit path)
- SLO: p95 < 2ms for cache hits; p95 < 20ms for cache misses

### 12.5 Billing Integrity SLO

- SLI: % of proxy requests that produce a billing event within 5 minutes
- SLO: 99.99%

### 12.6 Error Budget Policy

If an SLO error budget burn exceeds thresholds:

- freeze feature deploys
- prioritize reliability fixes
- escalate to “stability sprint”

---

## 13) Runbooks (Minimum Required)

Every P1/P2 alert must have a runbook link.
Operational runbooks: [runbooks/RUNBOOKS.md](runbooks/RUNBOOKS.md) (index: [runbooks/README.md](runbooks/README.md)).

Minimum runbooks:

- Proxy down
- Redis down / degraded
- Postgres failover
- ClickHouse down (buffering behavior)
- Auth validation failures spike
- Worker backlog
- Provider circuit breakers opening
- Suspected tenant isolation violation (P1)

Runbook template:

```markdown
# Runbook: <Alert Name>

## Symptoms
- ...

## Likely Causes
- ...

## Immediate Actions (first 15 minutes)
1. ...
2. ...

## Diagnosis
- commands / queries
- dashboards to check
- logs to filter

## Mitigation
- steps to reduce impact

## Recovery
- how to restore normal

## Follow-ups
- what to fix permanently
```

---

## 14) “Why did my agent do that?” Debugging View (Observability Requirement)

A key product promise is explainability:

For any inference trace, we must be able to show:

- directive version used
- memories retrieved and injected
- ranking scores (at least composite + components)
- token budget breakdown
- tool calls detected
- outcome/feedback signals if present

Required data sources:

- ClickHouse inference_traces: timings, token counts, memory_ids
- ClickHouse memory_access_log: per-memory scores and ranks
- Postgres directive_versions: content hash/version id
- Postgres sessions/checkpoints/events: timeline reconstruction

This view must be accessible in the dashboard and must not require log scraping.

---

## 15) Verification Checklist (Observability “Done” Criteria)

Before any service is considered production-ready:

- [ ] `/metrics` endpoint exists and is scraped
- [ ] request rate, error rate, latency metrics exist
- [ ] logs are structured JSON and include trace_id/request_id
- [ ] OTel traces propagate across boundaries
- [ ] at least one Grafana dashboard exists for the service
- [ ] alerts exist for the service’s key failure modes
- [ ] runbooks exist for P1/P2 alerts
- [ ] no high-cardinality metric labels are used

---

This observability spec is part of correctness.
If it isn’t measurable, it isn’t operable.
