DROP TRIGGER IF EXISTS provider_credentials_updated_at ON ibex_core.provider_credentials;
DROP POLICY IF EXISTS provider_credentials_isolation ON ibex_core.provider_credentials;
DROP TABLE IF EXISTS ibex_core.provider_credentials;
