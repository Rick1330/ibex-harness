DROP POLICY IF EXISTS organization_invites_isolation ON ibex_core.organization_invites;
ALTER TABLE ibex_core.organization_invites DISABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE ibex_core.organization_invites FROM ibex_app;
DROP TABLE IF EXISTS ibex_core.organization_invites;
