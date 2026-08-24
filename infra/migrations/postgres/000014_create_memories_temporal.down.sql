-- Dev/test rollback only. Production is forward-only (ADR-0005).

DROP TRIGGER IF EXISTS memories_updated_at ON ibex_core.memories;
DROP TRIGGER IF EXISTS sessions_clear_memory_session_id ON ibex_core.sessions;
DROP FUNCTION IF EXISTS ibex_core.clear_memory_session_id();

DROP POLICY IF EXISTS memories_isolation ON ibex_core.memories;

ALTER TABLE ibex_core.memories DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_memories_content_hash;
DROP INDEX IF EXISTS idx_memories_agent_active;

DROP TABLE IF EXISTS ibex_core.memories;
