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

The Proxy profile is explicit in all values: `deployment.profile` must match `proxy.environment`, so changing only the Proxy setting cannot downgrade a staging or production overlay. Staging and production require an out-of-band Kubernetes Secret named `ibex-redis` with key `redis-url`. The chart marks this Secret reference required in those profiles; it does not create or provision credentials. Local development keeps the Secret optional.

The checked-in staging and production overlays intentionally contain sentinel image digests and are **not deployable**. Before any staging or production release, run `.github/scripts/check-helm-deployable.sh <overlay>` with the final artifact-pinned overlay; it renders the chart and rejects missing, malformed, or sentinel digests. Direct `helm upgrade` that bypasses the release preflight is not an approved deployment path. The repository currently has no automated Helm deployment workflow, so the overlay alone is not evidence of a production release.

## Rollback by digest

See `web/engineering/runbooks/RUNBOOK-4p5-rollback-by-digest.md`.

## Kyverno

Apply `policies/verify-images.yaml` after installing Kyverno on the drill cluster.
