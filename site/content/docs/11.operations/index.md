---
title: Operations
description: Metrics, traces, health, incidents, billing evidence, relay, and the Console.
audience: operator
status: PROVISIONAL
scope: provisional
verifiedDate: "2026-10-21"
sourceOfTruth: services/*/README.md; infra/monitoring; engineering/architecture-v2/00-status-and-evidence.md
---

Operate IBEX as a set of independent services with explicit dependency checks and bounded failure behavior. This section separates local operational evidence from hosted readiness.

::page-status{status="PROVISIONAL" verified="2026-10-21" note="Service observability is implemented; restore, HA, and full deletion evidence remain open"}
::

## Pages

- [Observability](/docs/operations/observability) — metrics, logs, tracing, and dashboards.
- [Traces and ClickHouse](/docs/operations/traces-and-clickhouse) — what is stored, what is not, and the tenant-filter limit.
- [Health checks](/docs/operations/health-checks) — liveness vs readiness for each service.
- [Incident response](/docs/operations/incident-response) — severity, containment, and communication.
- [Troubleshooting](/docs/operations/troubleshooting) — common local failures.
- [Billing and budgets](/docs/operations/billing-and-budgets) — rate cards, usage facts, and hard-cap holds.
- [Evidence and relay](/docs/operations/evidence-and-relay) — outbox, fencing, projection, and recovery gaps.
- [Console](/docs/operations/console) — canonical operator app and its preview/live boundary.
- [Failure modes and recovery](/docs/operations/failure-and-recovery) — authority versus quality failures, restore classes, and drain behavior.
- [Data lifecycle and deletion](/docs/operations/data-lifecycle-and-deletion) — tombstones, organization deletion receipts, and legal holds.

## Operational truth

| Building block | Status | Must not be inferred |
| --- | --- | --- |
| Prometheus metrics | IMPLEMENTED | A measured hosted p99 |
| OpenTelemetry tracing | IMPLEMENTED | Complete trace coverage |
| Structured logs | IMPLEMENTED | Content-safe logging by default |
| Health/readiness | IMPLEMENTED | Graceful degradation under all failures |
| Backup/restore | PROVISIONAL | Tested RPO/RTO |
| HA/failover | PROVISIONAL | Multi-zone availability |
| Budget holds | PROVISIONAL | Exactly-once billing |
| Evidence relay | PROVISIONAL | Production sink delivery |

## Golden signals

For the proxy: request rate, error rate by code, latency, rate-limit denials, auth validation latency, provider latency, context fallback rate, and budget denials. For workers: queue depth, task failures, dead letters, and enqueue conflicts. For memory: write stage failures, dedup outcomes, search latency, and index usage. For auth: validation latency and failure reasons.

Never use `org_id`, `agent_id`, or request IDs as Prometheus labels. Those belong in logs and traces, not metric dimensions.
