-- Dev/test rollback only. Production is forward-only (ADR-0005).

DROP FUNCTION IF EXISTS ibex_core.resolve_supersession_tip(uuid, uuid, integer);

DROP VIEW IF EXISTS ibex_core.memory_supersession_edges;

DROP POLICY IF EXISTS memory_relationships_isolation ON ibex_core.memory_relationships;

ALTER TABLE ibex_core.memory_relationships DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_memory_relationships_org_source_type;
DROP INDEX IF EXISTS idx_memory_relationships_org_target_type;

DROP TABLE IF EXISTS ibex_core.memory_relationships;
