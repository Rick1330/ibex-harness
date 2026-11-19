-- Rollback is safe only before any cache copy has been recorded or proven. Once a
-- `cache`/`cache_hot` receipt exists, it is the only evidence that the cached copy
-- was checked for that memory revision, and once a cache ref exists it is the only
-- address the consumer can reach. The narrowed CHECK cannot hold either, and
-- deleting them to make the rollback succeed would delete evidence — the same
-- reason 000073 and 000074 refuse. A recorded failed attempt is evidence too.
DO $$
BEGIN
    -- No service-account GUC: 000063 stopped every policy reading it. The guard
    -- reads as the owner, which RLS does not fence.
    IF EXISTS (
        SELECT 1 FROM ibex_core.erasure_store_receipts
        WHERE store IN ('cache','cache_hot')
    ) THEN
        RAISE EXCEPTION 'refusing destructive 000078 rollback after memory cache erasure receipts exist';
    END IF;
    IF EXISTS (
        SELECT 1 FROM ibex_core.memory_artifact_refs
        WHERE store IN ('cache','cache_hot')
    ) THEN
        RAISE EXCEPTION 'refusing destructive 000078 rollback after memory cache artifact refs exist';
    END IF;
    IF EXISTS (
        SELECT 1 FROM ibex_core.memory_lifecycle_outbox
        WHERE cache_eviction_state <> 'pending'
    ) THEN
        RAISE EXCEPTION 'refusing destructive 000078 rollback after a cache eviction failure was recorded';
    END IF;
END;
$$;

REVOKE UPDATE (cache_eviction_state, cache_eviction_error)
    ON ibex_core.memory_lifecycle_outbox FROM ibex_app;

ALTER TABLE ibex_core.memory_lifecycle_outbox
    DROP COLUMN cache_eviction_error,
    DROP COLUMN cache_eviction_state;

ALTER TABLE ibex_core.memory_artifact_refs
    DROP CONSTRAINT memory_artifact_refs_store_check;
ALTER TABLE ibex_core.memory_artifact_refs
    ADD CONSTRAINT memory_artifact_refs_store_check
    CHECK (store IN ('objectstore','clickhouse','session_event'));

ALTER TABLE ibex_core.erasure_store_receipts
    DROP CONSTRAINT erasure_store_receipts_store_check;
ALTER TABLE ibex_core.erasure_store_receipts
    ADD CONSTRAINT erasure_store_receipts_store_check
    CHECK (store IN ('postgres','clickhouse','objectstore','session_event'));
