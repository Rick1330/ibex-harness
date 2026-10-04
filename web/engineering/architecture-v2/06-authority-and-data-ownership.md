# Authority and Data Ownership

**Status:** `specified` target matrix.

| Store/component | Canonical role | Not authoritative for |
|---|---|---|
| PostgreSQL | Tenants, policy, provider registry, reservations, operations, lifecycle, outbox | Approximate search ranking |
| Redis | Namespaced cache, bounded counters/leases, hot projection | Durable auth, billing, audit, deletion truth |
| pgvector/full-text | Search projections | Visibility or semantic truth |
| ClickHouse | Tenant-filtered analytics/evidence projection | Sole audit authority |
| Object storage | Classified large/redacted artifacts and immutable model artifacts | Undeclared source of truth |
| Queue/Celery/streams | Delivery transport | Exactly-once semantics without idempotent effects |
| OpenTelemetry | Export/correlation | Durable audit ledger |
| Browser/Console | Presentation and API client | Policy or direct storage access |

## Store rules

- Every tenant store has explicit `org_id` or a documented global classification.
- Tombstones suppress reads immediately even when physical purge is asynchronous.
- Projections carry source/version IDs and are rebuildable or marked otherwise.
- Redis and ClickHouse failures cannot broaden visibility or authorize actions.
- Analytics queries are constructed with mandatory tenant predicates; raw unscoped query paths are rejected.
