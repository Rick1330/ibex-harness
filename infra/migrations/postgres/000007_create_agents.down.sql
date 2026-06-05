DROP TRIGGER IF EXISTS agents_updated_at ON ibex_core.agents;
DROP POLICY IF EXISTS agents_isolation ON ibex_core.agents;

ALTER TABLE ibex_core.agents DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_agents_tags;
DROP INDEX IF EXISTS idx_agents_status;
DROP INDEX IF EXISTS idx_agents_org_id;

DROP TABLE IF EXISTS ibex_core.agents;

