DROP TRIGGER IF EXISTS users_updated_at ON ibex_core.users;
DROP POLICY IF EXISTS users_isolation ON ibex_core.users;

ALTER TABLE ibex_core.users DISABLE ROW LEVEL SECURITY;

DROP INDEX IF EXISTS idx_users_email;
DROP INDEX IF EXISTS idx_users_org_id;

DROP TABLE IF EXISTS ibex_core.users;

