# Monitoring configs (ADR-0051)

| Path | Role |
|---|---|
| `prometheus/` | Scrape config + Phase 2.5 alert rules |
| `alertmanager/` | Local null-receiver Alertmanager config |
| `otel/` | Collector: OTLP → Tempo (+ Loki for OTLP logs) |
| `tempo/` | Local filesystem Tempo |
| `loki/` | Single-binary Loki |
| `grafana/provisioning/` | Datasources + dashboard provider |
| `grafana/dashboards/` | System Overview, Proxy Critical Path, Auth, Embedder/MCP |

Used by [`infra/compose/observability/`](../compose/observability/) and [`infra/helm/observability/`](../helm/observability/).
