-- Rollback is safe only before any ref has been recorded. Once a row exists it is
-- the only evidence that an external copy (object-store object, ClickHouse
-- evidence, session event) belongs to a memory, and no other table can rebuild
-- it: the archive key is not derivable from the memory and the capture event does
-- not name the memory once this table is gone. Dropping the table therefore makes
-- those copies permanently unreachable for erasure, which is exactly the gap this
-- migration exists to close. Refuse instead of losing it silently.
DO $$
BEGIN
    -- No service-account GUC: 000063 stopped every policy reading it.
    IF EXISTS (SELECT 1 FROM ibex_core.memory_artifact_refs) THEN
        RAISE EXCEPTION 'refusing destructive 000072 rollback after memory artifact refs exist';
    END IF;
END;
$$;

DROP POLICY IF EXISTS memory_artifact_refs_isolation ON ibex_core.memory_artifact_refs;
DROP TABLE IF EXISTS ibex_core.memory_artifact_refs;
