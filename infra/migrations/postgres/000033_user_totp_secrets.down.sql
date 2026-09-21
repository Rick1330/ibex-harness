DROP TRIGGER IF EXISTS user_totp_secrets_updated_at ON ibex_core.user_totp_secrets;
DROP POLICY IF EXISTS user_totp_secrets_isolation ON ibex_core.user_totp_secrets;
DROP TABLE IF EXISTS ibex_core.user_totp_secrets;
