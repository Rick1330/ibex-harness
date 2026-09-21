-- Milestone 4.P.1: TOTP secrets for operator step-up (decision 1).

CREATE TABLE ibex_core.user_totp_secrets (
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,
    user_id         UUID NOT NULL
                    REFERENCES ibex_core.users(id)
                    ON DELETE CASCADE,
    ciphertext      BYTEA NOT NULL,
    wrapped_dek     BYTEA NOT NULL,
    encryption_key_id TEXT NOT NULL,
    confirmed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (org_id, user_id)
);

ALTER TABLE ibex_core.user_totp_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.user_totp_secrets FORCE ROW LEVEL SECURITY;

CREATE POLICY user_totp_secrets_isolation ON ibex_core.user_totp_secrets
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.user_totp_secrets TO ibex_app;

CREATE TRIGGER user_totp_secrets_updated_at
    BEFORE UPDATE ON ibex_core.user_totp_secrets
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
