-- Rollback is safe only before a consumer has acted on any row. Once a row
-- records erasure progress, dropping these columns destroys the only record that
-- the erasure was attempted: `partial` becomes indistinguishable from "never
-- ran", and a store that was already cleared is cleared again with no proof that
-- it was ever verified. `session_event` receipts are the same problem one level
-- down — the narrowed CHECK cannot hold them, and deleting them to make the
-- rollback succeed would delete evidence. Refuse instead of losing it silently.
DO $$
BEGIN
    -- No service-account GUC here: 000063 stopped every policy reading
    -- `app.is_service_account`, so setting it would be a bypass that no longer
    -- bypasses anything. The guard reads as the owner, which RLS does not fence.
    IF EXISTS (
        SELECT 1 FROM ibex_core.memory_lifecycle_outbox
        WHERE erasure_state <> 'pending' OR erasure_deadline IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'refusing destructive 000074 rollback after memory lifecycle erasure state exists';
    END IF;
    IF EXISTS (
        SELECT 1 FROM ibex_core.erasure_store_receipts WHERE store = 'session_event'
    ) THEN
        RAISE EXCEPTION 'refusing destructive 000074 rollback after session_event erasure receipts exist';
    END IF;
END;
$$;

REVOKE UPDATE ON ibex_core.memory_lifecycle_outbox FROM ibex_app;
REVOKE SELECT (id) ON ibex_core.session_events FROM ibex_purge;
DROP FUNCTION IF EXISTS ibex_core.memory_lifecycle_claim_erasure(
    INTEGER, DOUBLE PRECISION, DOUBLE PRECISION);

ALTER TABLE ibex_core.erasure_store_receipts
    DROP CONSTRAINT erasure_store_receipts_store_check;
ALTER TABLE ibex_core.erasure_store_receipts
    ADD CONSTRAINT erasure_store_receipts_store_check
    CHECK (store IN ('postgres','clickhouse','objectstore'));

ALTER TABLE ibex_core.memory_lifecycle_outbox
    DROP COLUMN erasure_deadline,
    DROP COLUMN erasure_state;
