# ADR-0021: Prometheus Metric Catalog (Phase 1)

**Status:** Accepted  
**Date:** 2026-06-07  
**Milestone:** [1.3.2](../roadmap/phase-1-core-platform/milestones/1.3.2-prometheus-metric-catalog.md)

## Context

Auth and proxy exposed `/metrics` via duplicate custom mutex-based implementations with inconsistent metric names, histogram buckets, and high-cardinality `path` labels (raw URLs with UUIDs). Cursor rules ([18-observability.mdc](../../.cursor/rules/18-observability.mdc), [29-ibex-packages.mdc](../../.cursor/rules/29-ibex-packages.mdc)) require a shared `packages/metrics` registry.

M1.3.1 initialized OTel tracing ([ADR-0019](ADR-0019-opentelemetry-provider-configuration.md)). Phase 1 Prometheus exposition uses `prometheus/client_golang` directly — not the OTel meter bridge.

## Decision

### 1) Single registration point

All Prometheus metrics are defined and registered in `packages/metrics`. Services call exported methods on `*ProxyRegistry` or `*AuthRegistry`; they never call `prometheus.MustRegister` directly.

### 2) Naming convention

`ibex_{service}_{noun}_{unit}` — e.g. `ibex_proxy_request_duration_seconds`.

### 3) Phase 1 catalog

| Metric | Type | Labels | Service |
| --- | --- | --- | --- |
| `ibex_proxy_request_duration_seconds` | Histogram | `route`, `method`, `status_code` | proxy |
| `ibex_proxy_requests_total` | Counter | `route`, `method`, `status_code` | proxy |
| `ibex_proxy_active_connections` | Gauge | — | proxy |
| `ibex_proxy_rate_limited_total` | Counter | `result` (`allowed`/`denied`) | proxy |
| `ibex_proxy_rate_limit_redis_errors_total` | Counter | — | proxy |
| `ibex_auth_validate_token_duration_seconds` | Histogram | `result` (`ok`/`error`/`revoked`) | auth |
| `ibex_auth_validate_agent_duration_seconds` | Histogram | `result` (`ok`/`error`/`not_found`) | auth |
| `ibex_auth_grpc_requests_total` | Counter | `method`, `status` | auth |
| `ibex_auth_http_request_duration_seconds` | Histogram | `route`, `method`, `status_code` | auth |
| `ibex_auth_http_requests_total` | Counter | `route`, `method`, `status_code` | auth |
| `ibex_db_query_duration_seconds` | Histogram | `operation` | auth |
| `ibex_db_pool_open_connections` | Gauge | `state` (`in_use`/`idle`) | auth |
| `ibex_process_up` | Gauge | `service` | both |

### 4) Label rules

- **`route`:** Go 1.22+ route template (`r.Pattern`), recorded after `ServeMux` dispatch. Never raw `r.URL.Path`.
- **`status_code`:** HTTP status as string (`"200"`, `"429"`).
- **`result`:** Bounded enums only — never dynamic error strings.
- **Forbidden labels:** `org_id`, `agent_id`, `user_id`, `session_id` — per-entity breakdowns belong in ClickHouse (Phase 3).

### 5) Histogram buckets

All latency histograms use `packages/metrics.LatencyBuckets`:

```text
0.001, 0.005, 0.010, 0.020, 0.050, 0.100, 0.250, 0.500, 1.000, 5.000
```

Tuned for the <20ms proxy overhead target.

### 6) Exposition

`/metrics` on each service uses `promhttp.HandlerFor(registry, promhttp.HandlerOpts{})`. Content-Type is set by promhttp.

### 7) Middleware order

**Proxy** (outer → inner): `RequestContext → Span → metrics → ResponseHeaders → logging → mux`.

Metrics middleware must run after `RequestContext` and `Span` (both call `r.WithContext`) so `http.ServeMux` sets `r.Pattern` on the same request pointer the metrics middleware observes. See `TestHTTPMiddleware_RecordsRouteTemplate`.

**Auth HTTP:** `AuthHTTPMiddleware` records `ibex_auth_http_*` on the auth HTTP router (health, metrics, etc.).

### 8) ValidateAgent status vs metric labels

`ValidateAgent` returns gRPC `PermissionDenied` when the agent record is missing or belongs to another org (`GetByIDAndOrg` returns nil). This follows multi-tenant isolation rules (no `NotFound` that leaks cross-org existence). The histogram label `result=not_found` is used for observability only and does not mirror the gRPC status code.

### 9) Validate timing location

`ibex_auth_validate_token_duration_seconds` and `ibex_auth_validate_agent_duration_seconds` are recorded on the **auth gRPC server**. Proxy-side `ibex_proxy_auth_validate_*` and `ibex_proxy_agent_validate_*` metrics are **retired** (supersedes [ADR-0011](ADR-0011-proxy-auth-client.md) §8 proxy metric names).

Rate-limit metrics deferred in [ADR-0015](ADR-0015-proxy-rate-limit-skeleton.md) §7 are implemented in M1.3.2.

## Consequences

### Positive

- Standard Prometheus scrape format; CI can validate with `expfmt` parser
- Single catalog; consistent buckets and naming
- Route-template labels align with OTel span `http.route`

### Negative

- Breaking change for anyone scraping old `ibex_http_*` or proxy validate metric names
- Token admin counters (`ibex_auth_token_*`) removed from Phase 1 catalog scope

## References

- [Milestone 1.3.2](../roadmap/phase-1-core-platform/milestones/1.3.2-prometheus-metric-catalog.md)
- [ADR-0019](ADR-0019-opentelemetry-provider-configuration.md)
- [ADR-0015](ADR-0015-proxy-rate-limit-skeleton.md)
