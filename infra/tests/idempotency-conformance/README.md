# request-idempotency-core.v1 conformance suite

Cross-runtime evidence that every IBEX mutating runtime which admits requests
through `ibex_core.idempotency_ledger` obeys the same durable claim contract:

| Runtime | Surface | Ledger |
| --- | --- | --- |
| proxy (Go) | `POST /v1/sessions/{id}/terminate`, non-streaming `/v1/chat/completions` | `packages/idempotency.PostgresLedger` |
| worker (Go) | `/internal/extraction/enqueue` | `packages/idempotency.PostgresLedger` |
| worker (Python) | enqueue facade (`app/idempotency_ledger.py`) | `ibex_idempotency.PostgresIdempotencyLedger` |
| memory (Python) | `POST /v1/memories` | `ibex_idempotency.PostgresIdempotencyLedger` |

## What this covers

* **Ledger semantics** (real PostgreSQL): owned → finalized → replay, conflict on
  a reused key with a different body, in-progress with a retry hint, lease
  reclaim that fences the stale owner, release/reopen, per-`(org, agent, key)`
  scope, and RLS isolation between orgs.
* **Crash/replay recovery**: a claim committed by a process that dies before
  `finalize` is recovered after lease expiry by a restarted ledger instance, and
  the stale owner is fenced off.
* **Fingerprint vector**: the frozen `request-idempotency-core.v1` canonical
  bytes, so JSON canonicalization drift is caught here first.

The Go side of the conformance evidence lives in
`packages/idempotency/ledger_postgres_integration_test.go` (`-tags=integration`).

## Running locally

```bash
# compose-test Postgres on :5433, migrated to head:
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  bash infra/scripts/idempotency-conformance-ci.sh
```

The suite skips (does not fail) when no DSN is set or PostgreSQL is unreachable.
