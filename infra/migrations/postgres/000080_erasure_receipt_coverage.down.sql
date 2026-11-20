-- Rollback is safe only before any receipt records a coverage set. That column is
-- the only record of which addresses a proof covered; dropping it turns an
-- address-aware receipt back into one that covers nothing, and a retry would
-- re-stage a store an earlier run already cleared. The same reason 000073 and
-- 000078 refuse.
--
-- A NULL coverage loses no information (it already covers no address), so the
-- guard refuses only on a non-NULL set.
--
-- The guard cannot lean on reading as the table owner. The table is ENABLE and
-- FORCE row level security (000073:35-40) with `USING rls_org_visible(org_id)`,
-- and that helper (000063) is true only for `ibex_service` or a matching
-- `app.current_org_id` GUC — neither of which a migration session sets. So a
-- migrate role subject to the policy sees zero rows here. With
-- `row_security = off` a query the policy would filter *raises* instead of
-- returning zero rows, which makes an unprivileged migrate role fail closed
-- rather than drop a column whose contents it could not read.
--
-- Transaction scope, measured on PostgreSQL 16.15 through the path this file is
-- run on: golang-migrate's Postgres driver hands the whole file to one
-- zero-argument `ExecContext`, which lib/pq sends as a single simple-query
-- message, and PostgreSQL executes a multi-statement simple query as one
-- implicit transaction. So these statements are atomic — a raise in the guard
-- rolls back every statement before it — but they are not an explicit transaction
-- block. Hence `SET`, not `SET LOCAL`, for both settings:
--
--   * `SET` is session scope and survives the implicit commit: `SHOW
--     lock_timeout` still reports the set value on the same connection once the
--     file has finished. That is why each setting is `RESET` at the end — the
--     driver reuses one connection for consecutive migration steps.
--   * `SET LOCAL` does take effect inside this file (the multi-statement message
--     is the nearest transaction block it can bind to) but warns "SET LOCAL can
--     only be used in transaction blocks" and changes nothing when the same
--     setting is executed as its own single-statement message. Keeping `SET`
--     means the `row_security = off` half of the guard cannot silently degrade
--     into a no-op, which would let a fenced role read zero rows and drop the
--     column.
--
-- The lock is what closes the window between the guard's read and the DROP. The
-- guard's `SELECT` alone takes ACCESS SHARE, which does not conflict with the
-- ROW EXCLUSIVE a worker holds while it commits its first non-NULL coverage: the
-- guard reads, a writer commits, `DROP COLUMN` then waits for that writer and is
-- granted the lock once it is gone, so the column holding the only record of the
-- addresses that worker proved absent is dropped on a stale verdict. Taking
-- ACCESS EXCLUSIVE before the guard instead puts the guard's read and the DROP
-- inside a transaction no writer can enter: a writer already in flight finishes
-- (commits or rolls back) before the lock is granted, so its commit is visible to
-- the guard's READ COMMITTED snapshot, and a write attempted afterwards blocks
-- behind the lock. ACCESS EXCLUSIVE is the mode `DROP COLUMN` needs anyway.
--
-- `lock_timeout` bounds that wait and is set first, because it also bounds the
-- LOCK: `DROP COLUMN` takes ACCESS EXCLUSIVE on a table the erasure worker writes
-- continuously, so the wait is bounded (same intent as 000063:30 and 000075:28)
-- instead of queueing readers behind a lock the worker holds.

SET lock_timeout = '5s';
SET row_security = off;

LOCK TABLE ibex_core.erasure_store_receipts IN ACCESS EXCLUSIVE MODE;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM ibex_core.erasure_store_receipts
        WHERE covered_addresses IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'refusing destructive 000080 rollback after erasure receipt coverage exists';
    END IF;
END;
$$;

RESET row_security;

ALTER TABLE ibex_core.erasure_store_receipts
    DROP COLUMN covered_addresses;

RESET lock_timeout;
