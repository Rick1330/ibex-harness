# IBEX Observability Helm chart (ADR-0051)

Thin Kubernetes packaging of the local LGTM stack used by Phase 2.5 exit.
**Out of scope:** full `ibex-harness` application Helm (proxy/auth/memory/…) — Phase 4+.

## kind / minikube

Default chart settings match compose: **anonymous Grafana Admin**, no embedded login secrets,
`automountServiceAccountToken: false`, and memory limits on every container.

```bash
# kind
kind create cluster --name ibex-obs || true
helm upgrade --install ibex-obs ./infra/helm/observability

# Grafana NodePort
kubectl -n ibex-observability get svc grafana
# Open http://localhost:30300 (kind: kubectl port-forward svc/grafana 3000:3000 -n ibex-observability)
```

```bash
# minikube
minikube start
helm upgrade --install ibex-obs ./infra/helm/observability
minikube service grafana -n ibex-observability
```

To disable anonymous login, create a Secret with key `admin-password`, then:

```bash
helm upgrade --install ibex-obs ./infra/helm/observability \
  --set grafana.anonymousAdmin=false \
  --set grafana.existingSecret=grafana-admin
```

## Compose vs Helm

Prefer **`make observability-up`** for day-to-day local graphs (host-scrape of auth/proxy/embedder/mcp).
Use this chart to validate Kubernetes packaging and future ServiceMonitor wiring
(`values.yaml` → `serviceMonitor.enabled: true` when app charts exist).

Config parity for dashboards/rules: ship via ConfigMaps from [`infra/monitoring/`](../../monitoring/)
in a follow-up if operators need identical Grafana JSON inside the cluster; compose remains
the source of truth for Phase 2.5 exit dashboards.
