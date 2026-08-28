-- Dev/test rollback only. Production is forward-only (ADR-0005).

DROP POLICY IF EXISTS memory_conflict_escalations_isolation
    ON ibex_core.memory_conflict_escalations;

ALTER TABLE ibex_core.memory_conflict_escalations DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_memory_conflict_escalations_org_status_pending;

DROP TABLE IF EXISTS ibex_core.memory_conflict_escalations;
