DROP TRIGGER IF EXISTS org_deletion_jobs_updated_at ON ibex_core.org_deletion_jobs;
DROP POLICY IF EXISTS org_deletion_jobs_isolation ON ibex_core.org_deletion_jobs;
ALTER TABLE ibex_core.org_deletion_jobs DISABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE ibex_core.org_deletion_jobs FROM ibex_app;
DROP TABLE IF EXISTS ibex_core.org_deletion_jobs;
