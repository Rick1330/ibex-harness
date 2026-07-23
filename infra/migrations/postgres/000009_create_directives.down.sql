DROP TRIGGER IF EXISTS directives_updated_at ON ibex_core.directives;

DROP POLICY IF EXISTS directive_versions_isolation ON ibex_core.directive_versions;
DROP POLICY IF EXISTS directives_isolation ON ibex_core.directives;

ALTER TABLE ibex_core.directive_versions DISABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.directives DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_directive_versions_directive_id;
DROP INDEX IF EXISTS idx_directives_agent_id;

ALTER TABLE ibex_core.directives
    DROP CONSTRAINT IF EXISTS directives_active_version_id_fk;

DROP TABLE IF EXISTS ibex_core.directive_versions;
DROP TABLE IF EXISTS ibex_core.directives;
