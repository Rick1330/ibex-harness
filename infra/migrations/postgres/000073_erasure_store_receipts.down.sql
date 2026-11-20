-- Rollback is safe only before any receipt has been recorded. A receipt is the
-- only evidence that a store was checked for one memory revision; once it exists,
-- dropping the table turns "erased and verified" back into "erased, unverified",
-- and a retry cannot distinguish a store it never reached from one it cleared.
--
-- `row_security = off` is session scope, not `SET LOCAL`: golang-migrate runs a
-- migration file outside a transaction, where `SET LOCAL` is a warning and
-- changes nothing. With it on, a read the policy would filter raises instead of
-- returning zero rows, so a migrate role that cannot see every tenant fails
-- closed rather than dropping a table whose rows it never counted.
SET row_security = off;

DO $$
BEGIN
    -- No service-account GUC: 000063 stopped every policy reading it. The table
    -- is ENABLE and FORCE row level security (000073), so this read is *not*
    -- privileged by ownership: without an org GUC or the `ibex_service` identity
    -- the policy filters every row. `row_security = off` (above) turns that
    -- silent zero-row pass into an error for a role subject to the policy.
    IF EXISTS (SELECT 1 FROM ibex_core.erasure_store_receipts) THEN
        RAISE EXCEPTION 'refusing destructive 000073 rollback after erasure store receipts exist';
    END IF;
END;
$$;

RESET row_security;

DROP TRIGGER IF EXISTS erasure_store_receipts_updated_at
    ON ibex_core.erasure_store_receipts;
DROP POLICY IF EXISTS erasure_store_receipts_isolation ON ibex_core.erasure_store_receipts;
DROP TABLE IF EXISTS ibex_core.erasure_store_receipts;
