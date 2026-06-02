DROP POLICY IF EXISTS tokens_isolation ON ibex_core.tokens;
ALTER TABLE ibex_core.tokens DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS organizations_isolation ON ibex_core.organizations;
ALTER TABLE ibex_core.organizations DISABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE ibex_core.tokens FROM ibex_app;
REVOKE ALL ON TABLE ibex_core.organizations FROM ibex_app;
REVOKE USAGE ON SCHEMA ibex_core FROM ibex_app;

DROP ROLE IF EXISTS ibex_app;
