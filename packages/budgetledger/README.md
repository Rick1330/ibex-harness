# `packages/budgetledger`

Tenant-scoped durable admission-hold ledger for proxy hard-cap enforcement
(GAP-006, provisional `budget-reservation.v1` slice).

## Contract and ownership

This is a shared package, not a deployable process. Consumers must preserve its
tenant, authorization, error, and fail-closed boundaries; do not copy
security-sensitive helpers into a service.

The ledger stores one row per `(organization_id, agent_id, reservation_key)` in
`ibex_core.budget_reservations` (migration `000046`). Claims exist only while
the organization has an active `hard_cap` period in `ibex_billing.budget_periods`:

- `Claim` takes a per-org advisory lock, resolves the key row under `FOR UPDATE`,
  enforces the cap against `spent_cents_cached + SUM(live claimed holds)`, and
  persists the hold as `claimed` with a lease. Outcomes are typed:
  `owned`, `in_progress`, `conflict`, `exceeded`, `no_cap`.
- `Finalize` records the settled amount and a `complete`/`estimated`
  completeness marker. A provider without usage must finalize with
  `estimated`, never silently as actual.
- `Release` drops a hold without settlement (failed/canceled request).
- Finalize/release are idempotent for an identical repeat and return
  `ErrClaimClosed` otherwise; a reclaimed reservation must never be settled
  silently.
- Terminal rows are a durable audit record and are **excluded** from cap
  accounting; capacity is bounded by the rollup updating `spent_cents_cached`,
  so the window shows a bounded overshoot until the next reconcile (documented
  GAP-006 limitation, no new source of truth).
- Reclaims reset or expire stale rows in place; a periodic reaper (worker)
  marks abandoned claims `expired` only after a grace window past the lease, so
  a slow but live owner can still finalize.

Rejected without any query: missing `org_id`/`agent_id`, blank or overlong
(>256) key, blank request hash, negative estimate. Callers must map raw
database errors to a fail-closed unavailable response (HTTP 503,
`BUDGET_UNAVAILABLE`) and must never admit the request.

Status is **implemented in this repository** when source and tests are present;
this README does not claim hosted production readiness. GAP-006 remains open
until the end-to-end slice is verified and the contract is accepted by its
owner.

## Performance

The claim runs on the proxy admission path only for organizations whose
hard-cap profile is active; callers consult the budget cache first and skip the
ledger entirely for `!HasHardCap` orgs. For hard-cap orgs the claim is bounded
by one transaction with at most six statements (org scope, advisory lock,
period lookup, key lookup, hold sum, insert/reset), no retry loop, and one
small value type retained per request. Failures fail closed instead of
retrying, keeping worst-case latency deterministic.

## Verification

From the repository root:

```bash
go test -race ./packages/budgetledger/...
```

Integration evidence lives in the migration suite
(`infra/migrations/postgres/migrate_budget_reservations_integration_test.go`),
which exercises schema constraints and cross-tenant RLS on real PostgreSQL.
