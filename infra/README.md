# Infrastructure

Local development, migrations, observability, test environments, and deployment scaffolding for IBEX Harness. This tree documents checked-in topology; it does not imply production deployment, HA, or recovery evidence.

## Current components

| Path | Role | Status |
| --- | --- | --- |
| `compose/dev/` | Postgres/pgvector, Redis Stack, ClickHouse, MinIO, worker, and worker-beat local stack | **Shipped local topology** |
| `compose/test/` | Minimal Postgres + Redis integration stack on port 5433 | **Shipped test topology** |
| `compose/observability/` | Local Prometheus, Grafana, Tempo, Loki, OTel Collector, Alertmanager | **Shipped local observability** |
| `monitoring/` | Compose scrape/rules/provisioning/configuration files | **Shipped for local stack**; not automatically consumed by Helm |
| `helm/observability/` | Thin Kubernetes packaging for selected observability components | **Render/lint scaffolding**; no Alertmanager, dashboard/rule ConfigMap parity, or Compose logs-to-Loki parity |
| `helm/ibex-harness/` | Application chart templates and values | **Render/lint scaffolding**; sentinel digests, disabled migration image, and no bundled data plane |
| `migrations/` | Postgres and ClickHouse migrations | **Shipped/tested; apply only through approved environment workflow** |
| `scripts/` | Makefile, health, verification, evidence, and guard helpers | **Shipped tooling** |

## Local operations

```bash
make compose-dev-up
make db-migrate
make db-seed # local-only seed data; never use against production
make observability-up
make compose-test-up
```

The local stack is not a production HA claim. Organization-wide HA, multi-AZ retention, complete Helm deployment, GPU sidecars, chaos, and measured recovery remain gated or deferred beyond the current phase.

## Change policy

A new datastore, network boundary, GPU runtime, chart, or migration path requires source/test evidence, tenant/security review, and an ADR. Update this inventory and the affected service/package README in the same change.

## Production-readiness preparation

Production infrastructure/setup preparation is in scope, but no deployment is authorized by the current task. The [production-readiness audit and no-deploy workplan](../web/engineering/architecture-v2/22-production-readiness-no-deploy-plan.md) records the existing Helm, image, recovery, monitoring, and supply-chain foundation and its open acceptance gaps. It is not a deployment guide or production-readiness claim.

See [services inventory](../services/README.md), [package inventory](../packages/README.md), and [current roadmap state](../web/content/roadmap/current-state.mdx).
