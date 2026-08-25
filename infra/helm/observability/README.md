# IBEX Observability Helm chart (ADR-0051)

Thin Kubernetes packaging of the local LGTM stack used by Phase 2.5 exit.
**Out of scope:** full `ibex-harness` application Helm (proxy/auth/memory/…) — Phase 4+.

## kind / minikube

Default chart settings: **anonymous Grafana disabled**, no embedded login secrets,
`automountServiceAccountToken: false`, and memory limits on every container.
Enable anonymous Viewer (not Admin) only via `--set grafana.anonymousAdmin=true`.

```bash
# kind
kind create cluster --name ibex-obs || true
helm upgrade --install ibex-obs ./infra/helm/observability \
  --namespace ibex-observability --create-namespace

# Grafana via port-forward (do not rely on NodePort 30300 unless kind extraPortMappings are configured)
kubectl -n ibex-observability port-forward svc/grafana 3000:3000
# Open http://127.0.0.1:3000
```

```bash
# minikube
minikube start
helm upgrade --install ibex-obs ./infra/helm/observability \
  --namespace ibex-observability --create-namespace
kubectl -n ibex-observability port-forward svc/grafana 3000:3000
```

To use password login, create a Secret with key `admin-password`, then:

```bash
helm upgrade --install ibex-obs ./infra/helm/observability \
  --namespace ibex-observability --create-namespace \
  --set grafana.existingSecret=grafana-admin
```

## Compose vs Helm

Prefer **`make observability-up`** for day-to-day local graphs (host-scrape of auth/proxy/embedder/mcp).
Use this chart to validate Kubernetes packaging and future ServiceMonitor wiring
(`values.yaml` → `serviceMonitor.enabled: true` when app charts exist).

Config parity for dashboards/rules: ship via ConfigMaps from [`infra/monitoring/`](../../monitoring/)
in a follow-up if operators need identical Grafana JSON inside the cluster; compose remains
the source of truth for Phase 2.5 exit dashboards.
