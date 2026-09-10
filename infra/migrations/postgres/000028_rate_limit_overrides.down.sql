DROP TRIGGER IF EXISTS rate_limit_overrides_updated_at ON ibex_core.rate_limit_overrides;
DROP POLICY IF EXISTS rate_limit_overrides_isolation ON ibex_core.rate_limit_overrides;
DROP TABLE IF EXISTS ibex_core.rate_limit_overrides;
