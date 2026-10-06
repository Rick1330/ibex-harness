# Runtime Operations and Recovery

**Status:** `design-intent` / target; profile acceptance is pending evidence.

## Profile obligations

Development Compose documents convenience and local limitations. Single-node self-hosted documents backup, resource, and operator limits. HA production requires ownership, replicas/failover, secrets, network policy, backups, restore drills, SLOs, and support escalation.

### Current task scope selection

On 2026-10-06, the task owner selected **Development Compose only for local integration, with no production-support claim** ([issue #939](https://github.com/Rick1330/ibex-harness/issues/939)). This is a scope decision, not a `shipped-accepted` or production-support claim. The profile is defined in [`infra/compose/dev/docker-compose.yml`](../../../infra/compose/dev/docker-compose.yml); the active Sandbox had no Docker/Compose CLI, Podman, or Docker daemon socket, so the Compose stack was not run or validated in this task. Exact profile/dependency digests and a successful local integration run remain evidence requirements.

For this local-only scope, production backup/HA/support guarantees and numerical RPO/RTO targets are explicitly deferred; local development data is not represented as durable. If reset/reseed behavior is needed for repeatable integration tests, document and verify that separately—it is not production restore evidence. A future production-profile decision reopens the recovery requirements below.

## Recovery

Classify data into canonical Postgres/control, evidence/outbox, object artifacts, Redis projections, vector/search projections, and queues. Define backup consistency, encryption, key recovery, retention, immutable copies, restore ordering, and measured RPO/RTO per class. Caches and indexes must be rebuildable without widening access.

## Migrations

Use expand → dual-read/write → backfill → verify → contract. Define lock/statement timeouts, throttle/backpressure, restart/resume, abort criteria, roll-forward/rollback decision, and mixed-version compatibility. Embedding/profile changes are versioned migrations, never silent replacement.

## Operator readiness

Every service needs an owner, runbook, health/readiness/drain behavior, dashboards, alerts, capacity limits, secret rotation, backup/restore, migration, rollback, dependency-failure drill, and escalation path. No production guarantee is published from code presence alone.
