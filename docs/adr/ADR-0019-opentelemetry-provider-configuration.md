# ADR-0019: OpenTelemetry provider configuration (Phase 1)

- **Status:** Accepted
- **Date:** 2026-06-07
- **Authors:** IBEX Harness team

## Context

M1.3.3 delivered `packages/logger` with `trace_id` from `trace.SpanFromContext`, but no tracer provider was initialized — `trace_id` was always empty. ADR-0017 reserved synthetic `X-Trace-ID` (UUID v4) until OTel spans exist.

Phase 1 requires distributed tracing infrastructure without mandating a running Jaeger/Tempo collector. CI must assert spans via in-process recorders.

## Decision

### 1) Shared package `packages/telemetry`

Both `services/auth` and `services/proxy` initialize OTel via `telemetry.Init(ctx, cfg)` in `main.go`:

- `TracerProvider` and `MeterProvider` configured once at startup
- Global propagator: W3C `tracecontext` + `baggage`
- Tracers obtained via `providers.TracerProvider.Tracer("ibex-<service>")` — no `otel.Tracer()` in service code ([29-ibex-packages.mdc](../.cursor/rules/29-ibex-packages.mdc))

SDK: `go.opentelemetry.io/otel` v1.x (pinned in `go.mod`).

### 2) Resource attributes

Every span carries resource attributes:

| Attribute | Source |
| --- | --- |
| `service.name` | `OTEL_SERVICE_NAME` (fallback `IBEX_SERVICE_NAME`) |
| `service.version` | `OTEL_SERVICE_VERSION` (default `dev`) |
| `deployment.environment` | `OTEL_DEPLOYMENT_ENVIRONMENT` (fallback `IBEX_ENV`, default `development`) |

### 3) Exporter selection

| Condition | Behaviour |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` set | OTLP gRPC batch exporter |
| `OTEL_EXPORTER_OTLP_ENDPOINT` empty | No exporter — spans created for context propagation only (development/CI) |

Phase 1 does not require an external collector. Unit tests use `sdktrace/tracetest` in-memory exporter.

### 4) Sampling

Phase 1 uses `ParentBased(TraceIDRatioBased(OTEL_SAMPLE_RATIO))` with default ratio `0.01`.

Unconditional error-priority **export** sampling (100% of 5xx traces) requires tail-based sampling at the collector — deferred to Phase 2 per milestone non-goals. HTTP span middleware sets span status `ERROR` on HTTP status ≥ 500 on sampled spans.

### 5) HTTP span middleware

`telemetry.SpanMiddleware(tracer)` creates server spans named `{method} {route_template}` (e.g. `POST /v1/chat/completions`). Route template from `http.Request.Pattern` (Go 1.22+ ServeMux), never raw URL paths.

Attributes: `http.method`, `http.route`, `http.status_code`, `http.request_content_length`, `ibex.request_id`.

Middleware order (proxy):

```text
metrics → RequestContext → Span → ResponseHeaders → logging → mux
```

Protected route auth middleware runs inside mux after span creation.

### 6) gRPC client trace propagation

Proxy auth gRPC client uses `otelgrpc.UnaryClientInterceptor()` chained after `RequestIDUnaryInterceptor`. Auth gRPC server interceptors are out of scope until auth gains a full server test suite.

### 7) Synthetic trace ID retired (ADR-0017 amendment)

`RequestContextMiddleware` no longer generates synthetic UUID v4 trace IDs. `X-Trace-ID` response header is set from OTel `SpanContext.TraceID()` after span middleware runs.

Request ID (`packages/reqid`) remains the internal log correlation token.

### 8) Shutdown

`providers.Shutdown` is registered **first** on `packages/shutdown.Coordinator` (ADR-0018) to flush OTLP exporters before HTTP/gRPC drain.

## Environment variables

| Variable | Required | Default |
| --- | --- | --- |
| `OTEL_SERVICE_NAME` | Yes* | `IBEX_SERVICE_NAME` |
| `OTEL_SERVICE_VERSION` | No | `dev` |
| `OTEL_DEPLOYMENT_ENVIRONMENT` | No | `IBEX_ENV` or `development` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | (empty — noop) |
| `OTEL_SAMPLE_RATIO` | No | `0.01` |

\*Required directly or via `IBEX_SERVICE_NAME` fallback.

## Consequences

### Positive

- `packages/logger` `trace_id` populated on every HTTP request
- W3C `traceparent` propagation to auth gRPC calls from proxy
- No external collector required for CI or local dev
- M1.3.2 Prometheus migration can adopt initialized meter provider

### Negative

- 99% of successful requests not exported at default sampling (by design)
- Auth HTTP spans lack `ibex.request_id` until auth gains reqid middleware

## References

- [Milestone 1.3.1](../roadmap/phase-1-core-platform/milestones/1.3.1-otel-tracer-provider-init.md)
- [ADR-0017](ADR-0017-request-id-strategy.md)
- [ADR-0018](ADR-0018-graceful-shutdown.md)
- [18-observability.mdc](../.cursor/rules/18-observability.mdc)
