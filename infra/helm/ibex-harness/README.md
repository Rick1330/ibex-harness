# ibex-harness Helm chart (4.P.5)

Umbrella chart for proxy, auth, api, worker, memory, embedder, mcp-memory.

## Conventions

Matches `infra/helm/observability`: digest-pinned `images.*`, per-component resources, namespace via release.

## Render

```bash
helm lint infra/helm/ibex-harness
helm template ibex infra/helm/ibex-harness -f infra/helm/ibex-harness/values.yaml > /tmp/ibex-render.yaml
```

## Environments

- `values.yaml` — kind/k3d drill defaults
- `values-staging.yaml` / `values-prod.yaml` — overlays

## Rollback by digest

See `web/engineering/runbooks/RUNBOOK-4p5-rollback-by-digest.md`.

## Kyverno

Apply `policies/verify-images.yaml` after installing Kyverno on the drill cluster.
