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
-- rather than drop a column whose contents it could not read. It is session
-- scope, not `SET LOCAL`: golang-migrate runs a migration file outside a
-- transaction, where `SET LOCAL` is a warning and changes nothing.
--
-- `lock_timeout` is session scope for the same reason. `DROP COLUMN` takes
-- ACCESS EXCLUSIVE on a table the erasure worker writes continuously, so the
-- wait is bounded (same intent as 000063:30 and 000075:28) instead of queueing
-- readers behind a lock the worker holds.

SET lock_timeout = '5s';
SET row_security = off;

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
