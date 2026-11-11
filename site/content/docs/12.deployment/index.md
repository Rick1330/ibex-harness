---
title: Deployment
description: Local Compose, environment configuration, Kubernetes scaffolding, and the production-readiness gap.
audience: operator
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-11-07"
sourceOfTruth: infra/compose/dev; infra/helm; engineering/architecture-v2/00-status-and-evidence.md
---

IBEX Harness ships one supported single-node profile, `v1-single-node`, and a separate development dependency stack. It
does **not** ship a hosted or highly available deployment. This section explains exactly what exists and what must be
supplied before promotion.

::page-status{status="PROVISIONAL" verified="2026-11-07" note="v1-single-node is the supported deployment profile; hosted, HA, and production evidence remain open"}
::

## Pages

- [v1-single-node profile](/docs/deployment/v1-single-node) — the supported single-node deployment profile.
- [Docker Compose](/docs/deployment/docker-compose) — the development dependency stack.
- [Environment variables](/docs/deployment/environment-variables) — configuration registry and fail-closed rules.
- [Kubernetes](/docs/deployment/kubernetes) — render/lint scaffolding, sentinel digests, and missing data-plane templates.
- [Production readiness](/docs/deployment/production-readiness) — the promotion checklist and open gates.

## Runtime profiles

| Profile | What works | What is missing |
| --- | --- | --- |
| `v1-single-node` (supported) | One Compose project: edge TLS, all required services, three one-shot gates (`migrate`, `provision`, `bootstrap`), recorded readiness | Hosted/HA operation, multi-user auth, measured p99 SLO, cross-tenant acceptance, recovery drill, the DSN cutover onto the capability logins |
| Local (development) | Compose data stores; host-run Go/Python services | Nothing claimed beyond local evidence |
| Staging (Kubernetes) | Helm overlays render; external Secrets expected | Real digests, data-plane provisioning, migration execution, deployment workflow |
| Production (Kubernetes) | Chart scaffolding exists | Deployable defaults, data-plane templates, recovery evidence, SLO proof |

## Deployment rules

- Never use sentinel image digests for a real release.
- Never enable development-only behavior in staging or production.
- Never run mock mode in production.
- Never bypass release preflight with a direct `helm upgrade`.
- Never treat a rendered chart as a deployable artifact.
- Never place credentials in values files or browser-exposed configuration.
- Never claim HA because a Deployment replica count is greater than one.

## Supported local path

```bash
make compose-dev-up
make db-migrate
make db-seed
```

Then start auth before the proxy, and start Python services only when their surface is needed. See [Local development](/docs/getting-started/local-development).
