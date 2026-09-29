# Monitoring configuration (ADR-0051)

These files are the configuration and provisioning source for the **local Compose observability stack**. The Kubernetes chart is a separate thin packaging layer and does not automatically mount or mirror this tree.

| Path | Role |
| --- | --- |
| `prometheus/` | Scrape configuration and alert rules |
| `alertmanager/` | Local Alertmanager configuration |
| `otel/` | Collector pipelines for OTLP traces/logs |
| `tempo/` | Local filesystem Tempo configuration |
| `loki/` | Local single-binary Loki configuration |
| `grafana/provisioning/` | Local data sources and dashboard provider |
| `grafana/dashboards/` | Local dashboards |

## Parity boundary

`infra/compose/observability/` consumes these files. `infra/helm/observability/` currently does not provide Alertmanager, dashboard/rule/scrape ConfigMaps, or the Compose logs-to-Loki pipeline. Do not describe Helm installation as equivalent local LGTM coverage until those templates and acceptance tests exist.

Local observability is useful evidence for development and contract checks only. Production HA, multi-AZ retention, external alert routing, and measured recovery remain separate operational gates.
