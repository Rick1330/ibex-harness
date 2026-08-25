# Local LGTM observability (ADR-0051)

Bring up Prometheus, Grafana, Tempo, Loki, OpenTelemetry Collector, and Alertmanager
for Phase 2.5 exit / local operator work.

Host ports bind to **127.0.0.1** only (not LAN). Grafana anonymous role is **Viewer**.

## Quick start

```bash
make observability-up
# Point proxy/auth at the collector (host:port, no scheme):
#   export OTEL_EXPORTER_OTLP_ENDPOINT=127.0.0.1:4317
# Generate traffic (dev-smoke or verify-phase25), then:
make observability-smoke
```

| UI | URL (defaults from `.env.example`) |
|---|---|
| Grafana | http://127.0.0.1:3000 (loopback; anonymous Viewer) |
| Prometheus | http://127.0.0.1:19090 |
| Tempo | http://127.0.0.1:3200 |
| Loki | http://127.0.0.1:3100 |
| Alertmanager | http://127.0.0.1:9093 |
| OTLP gRPC | 127.0.0.1:4317 |

Configs live in [`infra/monitoring/`](../../monitoring/). Dashboards are provisioned under
Grafana → Dashboards → IBEX.

## Scraping host services

Prometheus scrapes `host.docker.internal` ports where auth/proxy/embedder/mcp-memory
publish `/metrics` when run on the host. Adjust targets in
[`infra/monitoring/prometheus/prometheus.yml`](../../monitoring/prometheus/prometheus.yml)
if you change listen ports.

Embedder `/metrics` requires a Bearer token. `make observability-up` writes
`infra/monitoring/prometheus/secrets/embedder_metrics_bearer` from
`IBEX_EMBEDDING_METRICS_BEARER` in `.env` (gitignored). Scrape jobs use
`authorization.credentials_file` — do not commit the secret file.

## Non-goals

Production HA, multi-cluster, full application Helm — see ADR-0051 and Phase 4+.
