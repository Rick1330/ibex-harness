DROP TRIGGER IF EXISTS sessions_updated_at ON ibex_core.sessions;
DROP TRIGGER IF EXISTS checkpoints_immutable ON ibex_core.checkpoints;
DROP FUNCTION IF EXISTS ibex_core.reject_checkpoint_update();

DROP POLICY IF EXISTS checkpoints_isolation ON ibex_core.checkpoints;
DROP POLICY IF EXISTS sessions_isolation ON ibex_core.sessions;

ALTER TABLE ibex_core.checkpoints DISABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.sessions DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_sessions_org_status;
DROP INDEX IF EXISTS idx_sessions_org_agent;
DROP INDEX IF EXISTS idx_checkpoints_session_turn;
DROP INDEX IF EXISTS idx_sessions_agent_extraction;
DROP INDEX IF EXISTS idx_sessions_org_agent_external_id;

DROP TABLE IF EXISTS ibex_core.checkpoints;
DROP TABLE IF EXISTS ibex_core.sessions;
