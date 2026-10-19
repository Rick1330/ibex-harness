# ibex-idempotency (Python)

Shared, canonical PostgreSQL request-idempotency ledger adapter for IBEX Python
services. It is the Python counterpart of the Go `packages/idempotency` ledger
and targets the same table (`ibex_core.idempotency_ledger`) and concurrency
semantics, so a claim taken by one runtime is observed identically by the other.

Contract: `request-idempotency-core.v1`.

## Layout

```text
packages/ibex_idempotency/
  pyproject.toml
  README.md
  src/
    ibex_idempotency/
      __init__.py         # public surface
      fingerprint.py      # canonical request hashing
      ledger.py           # PostgresIdempotencyLedger (claim/finalize/release)
      sessions.py         # tenant-scoped SQLAlchemy session helpers
  tests/
    test_fingerprint.py
    test_ledger_unit.py
```

## Consumers

`services/worker` (extraction enqueue) and `services/memory` (`POST /v1/memories`).
Both pin the package via a path dependency and build a trusted wheel in CI and
Docker images (`infra/scripts/build-ibex-idempotency-wheel.sh`).

```toml
[tool.uv.sources]
ibex-idempotency = { path = "../../packages/ibex_idempotency" }
```

## Semantics

- **Scope:** every claim is scoped to `(organization_id, agent_id, dedupe_key)`.
- **States:** `claimed`, `finalized`, `reconciling`, `failed_terminal`.
- **Lease:** a `claimed` row carries `lease_expires_at` (default 120s). An expired
  claim may be reclaimed by any caller; the previous owner's token version then
  fails to finalize or release.
- **Replay:** a `finalized` row returns the stored `status_code` and
  `response_payload`; a matching key with a different `request_hash` is a
  conflict.
- **Fail closed:** the adapter raises `LedgerError` when the ledger cannot admit
  or persist a mutation. Callers surface that as `503`, never as a silent
  no-op.

Rows are written as the platform actor with `app.current_org_id` (and
`app.is_service_account`) set explicitly for RLS defense-in-depth, even though
the ledger table also enforces row-level security.
