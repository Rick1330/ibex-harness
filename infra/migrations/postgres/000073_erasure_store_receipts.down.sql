-- Rollback is safe only before any receipt has been recorded. A receipt is the
-- only evidence that a store was checked for one memory revision; once it exists,
-- dropping the table turns "erased and verified" back into "erased, unverified",
-- and a retry cannot distinguish a store it never reached from one it cleared.
DO $$
BEGIN
    -- No service-account GUC: 000063 stopped every policy reading it.
    IF EXISTS (SELECT 1 FROM ibex_core.erasure_store_receipts) THEN
        RAISE EXCEPTION 'refusing destructive 000073 rollback after erasure store receipts exist';
    END IF;
END;
$$;

DROP TRIGGER IF EXISTS erasure_store_receipts_updated_at
    ON ibex_core.erasure_store_receipts;
DROP POLICY IF EXISTS erasure_store_receipts_isolation ON ibex_core.erasure_store_receipts;
DROP TABLE IF EXISTS ibex_core.erasure_store_receipts;
