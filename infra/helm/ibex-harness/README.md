# ibex-harness Helm chart (4.P.5)

Umbrella chart scaffolding for proxy, auth, api, worker, memory, embedder, and mcp-memory.

## Conventions

Matches `infra/helm/observability`: digest-shaped `images.*`, per-component resources, namespace via release. The checked-in values are render/lint scaffolding, not deployable artifacts.

## Render

```bash
helm lint infra/helm/ibex-harness
helm template ibex infra/helm/ibex-harness -f infra/helm/ibex-harness/values.yaml > /tmp/ibex-render.yaml
```

## Environments

- `values.yaml` — kind/k3d drill defaults
- `values-staging.yaml` / `values-prod.yaml` — overlays

The Proxy profile is explicit in all values: `deployment.profile` must match `proxy.environment`, so changing only the Proxy setting cannot downgrade a staging or production overlay. Staging and production require an out-of-band Kubernetes Secret named `ibex-redis` with key `redis-url`. The chart marks this Secret reference required in those profiles; it does not create or provision credentials. Local development keeps the Secret optional.

The checked-in default, staging, and production values intentionally contain sentinel image digests; the migration image is disabled and the chart has no Postgres/Redis/ClickHouse/MinIO data-plane templates. They are **not deployable defaults**. Before any staging or production release, provide real artifact digests, external Secrets, data-plane provisioning, and migration execution, then run `.github/scripts/check-helm-deployable.sh <overlay>`. Direct `helm upgrade` that bypasses release preflight is not approved. The repository currently has no automated Helm deployment workflow, so an overlay is not production-release evidence.

## Rollback by digest

See `web/engineering/runbooks/RUNBOOK-4p5-rollback-by-digest.md`.

## Kyverno

Apply `policies/verify-images.yaml` after installing Kyverno on the drill cluster.
