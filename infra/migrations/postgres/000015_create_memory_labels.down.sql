-- Dev/test rollback only. Production is forward-only (ADR-0005).

DROP TRIGGER IF EXISTS memory_labels_sync_primary_category ON ibex_core.memory_labels;
DROP FUNCTION IF EXISTS ibex_core.sync_memory_primary_category();

DROP POLICY IF EXISTS memory_labels_isolation ON ibex_core.memory_labels;

ALTER TABLE ibex_core.memory_labels DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_memory_labels_org_label;

DROP TABLE IF EXISTS ibex_core.memory_labels;
