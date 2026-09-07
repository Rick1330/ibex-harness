-- Dev/test rollback only. Production is forward-only (ADR-0005).

DROP TRIGGER IF EXISTS memory_feedback_updated_at ON ibex_core.memory_feedback;

DROP POLICY IF EXISTS memory_feedback_isolation
    ON ibex_core.memory_feedback;

ALTER TABLE ibex_core.memory_feedback DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_memory_feedback_org_memory;

DROP TABLE IF EXISTS ibex_core.memory_feedback;
