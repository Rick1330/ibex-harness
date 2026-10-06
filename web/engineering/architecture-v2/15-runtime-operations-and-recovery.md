# Runtime Operations and Recovery

**Status:** `design-intent` / target; profile acceptance is pending evidence.

## Profile obligations

Development Compose documents convenience and local limitations. Single-node self-hosted documents backup, resource, and operator limits. HA production requires ownership, replicas/failover, secrets, network policy, backups, restore drills, SLOs, and support escalation.

### Current task scope selection

On 2026-10-06, the task owner first selected Development Compose for local integration, then expanded the task to production-readiness infrastructure/setup and explicitly prohibited deployment ([issue #939](https://github.com/Rick1330/ibex-harness/issues/939)). The selected preparation direction is a provider-neutral Kubernetes/Helm application profile with external data-plane interfaces; provider-specific IaC is deferred, and no HA/support claim is made until evidence exists. Development Compose remains the local profile. This is not G0 acceptance, a validated/supported production profile, or production-support evidence; actual data-plane implementations and topology remain unresolved. See the [production infrastructure audit and no-deploy workplan](22-production-readiness-no-deploy-plan.md). The profile is defined in [`infra/compose/dev/docker-compose.yml`](../../../infra/compose/dev/docker-compose.yml); the active Sandbox had no Docker/Compose CLI, Podman, or Docker daemon socket, so the Compose stack was not run or validated. Exact profile/dependency digests and a successful local integration run remain evidence requirements.

Production recovery and operator-readiness preparation is now in scope, but numerical RPO/RTO, SLO, retention, key-ownership, support, and topology decisions remain unaccepted. The existing 4.P.5 values are working targets only; they are not measured results. Local development data remains disposable and is not production restore evidence. Any production-support claim still requires a named profile, owner-approved objectives, and profile-specific recovery evidence.

## Recovery

Classify data into canonical Postgres/control, evidence/outbox, object artifacts, Redis projections, vector/search projections, and queues. Define backup consistency, encryption, key recovery, retention, immutable copies, restore ordering, and measured RPO/RTO per class. Caches and indexes must be rebuildable without widening access.

## Migrations

Use expand → dual-read/write → backfill → verify → contract. Define lock/statement timeouts, throttle/backpressure, restart/resume, abort criteria, roll-forward/rollback decision, and mixed-version compatibility. Embedding/profile changes are versioned migrations, never silent replacement.

## Operator readiness

Every service needs an owner, runbook, health/readiness/drain behavior, dashboards, alerts, capacity limits, secret rotation, backup/restore, migration, rollback, dependency-failure drill, and escalation path. No production guarantee is published from code presence alone.
