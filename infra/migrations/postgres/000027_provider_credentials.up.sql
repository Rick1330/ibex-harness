-- Milestone 4.A.5: org-scoped provider API keys (envelope-encrypted at rest).
CREATE TABLE ibex_core.provider_credentials (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE CASCADE,
    provider_name       TEXT NOT NULL
                        CHECK (provider_name IN (
                            'openai',
                            'anthropic',
                            'azure_openai',
                            'bedrock',
                            'vllm_self_hosted'
                        )),

    -- Envelope: nonce(12) || AES-GCM ciphertext (includes tag). Never plaintext.
    ciphertext          BYTEA NOT NULL,
    wrapped_dek         BYTEA NOT NULL,
    encryption_key_id   TEXT NOT NULL,
    key_hint            TEXT NOT NULL,

    base_url            TEXT,
    status              TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'disabled', 'invalid')),
    last_validated_at   TIMESTAMPTZ,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (org_id, provider_name)
);

CREATE INDEX idx_provider_credentials_org_id
    ON ibex_core.provider_credentials(org_id);

ALTER TABLE ibex_core.provider_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.provider_credentials FORCE ROW LEVEL SECURITY;

CREATE POLICY provider_credentials_isolation ON ibex_core.provider_credentials
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.provider_credentials TO ibex_app;

CREATE TRIGGER provider_credentials_updated_at
    BEFORE UPDATE ON ibex_core.provider_credentials
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
