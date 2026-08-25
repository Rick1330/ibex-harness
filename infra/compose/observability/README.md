# Local LGTM observability (ADR-0051)

Bring up Prometheus, Grafana, Tempo, Loki, OpenTelemetry Collector, and Alertmanager
for Phase 2.5 exit / local operator work.

## Quick start

```bash
make observability-up
# Point proxy/auth at the collector:
#   export OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4317
# Generate traffic (dev-smoke or verify-phase25), then:
make observability-smoke
```

| UI | URL (defaults) |
|---|---|
| Grafana | http://localhost:3000 (anonymous Admin) |
| Prometheus | http://localhost:9090 |
| Tempo | http://localhost:3200 |
| Loki | http://localhost:3100 |
| Alertmanager | http://localhost:9093 |
| OTLP gRPC | localhost:4317 |

Configs live in [`infra/monitoring/`](../../monitoring/). Dashboards are provisioned under
Grafana → Dashboards → IBEX.

## Scraping host services

Prometheus scrapes `host.docker.internal` ports where auth/proxy/embedder/mcp-memory
publish `/metrics` when run on the host. Adjust targets in
[`infra/monitoring/prometheus/prometheus.yml`](../../monitoring/prometheus/prometheus.yml)
if you change listen ports.

Embedder `/metrics` requires `Authorization: Bearer <IBEX_EMBEDDING_API_TOKEN>`. Set
`IBEX_EMBEDDING_METRICS_BEARER` in `.env` (copied from `.env.example`) to match.

## Non-goals

Production HA, multi-cluster, full application Helm — see ADR-0051 and Phase 4+.
