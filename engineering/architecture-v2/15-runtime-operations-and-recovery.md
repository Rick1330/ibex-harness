# Runtime Operations and Recovery

**Status:** `design-intent` / target; profile acceptance is pending evidence.

## Profile obligations

Development Compose documents convenience and local limitations. Single-node self-hosted documents backup, resource, and operator limits. HA production requires ownership, replicas/failover, secrets, network policy, backups, restore drills, SLOs, and support escalation.

## Recovery

Classify data into canonical Postgres/control, evidence/outbox, object artifacts, Redis projections, vector/search projections, and queues. Define backup consistency, encryption, key recovery, retention, immutable copies, restore ordering, and measured RPO/RTO per class. Caches and indexes must be rebuildable without widening access.

## Migrations

Use expand → dual-read/write → backfill → verify → contract. Define lock/statement timeouts, throttle/backpressure, restart/resume, abort criteria, roll-forward/rollback decision, and mixed-version compatibility. Embedding/profile changes are versioned migrations, never silent replacement.

## Operator readiness

Every service needs an owner, runbook, health/readiness/drain behavior, dashboards, alerts, capacity limits, secret rotation, backup/restore, migration, rollback, dependency-failure drill, and escalation path. No production guarantee is published from code presence alone.
