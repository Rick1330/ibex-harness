CREATE TABLE ibex_core.tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,
    user_id         UUID,
    agent_id        UUID,

    type            TEXT NOT NULL
                    CHECK (type IN (
                        'pat',
                        'org_token',
                        'service_token',
                        'marketplace'
                    )),

    hash            TEXT NOT NULL UNIQUE,
    prefix          TEXT NOT NULL,

    name            TEXT NOT NULL,
    description     TEXT,

    permissions     BIGINT NOT NULL,

    expires_at      TIMESTAMPTZ,

    is_revoked      BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at      TIMESTAMPTZ,
    revoked_by      UUID,
    revoke_reason   TEXT,

    last_used_at    TIMESTAMPTZ,
    last_used_ip    INET,
    use_count       BIGINT NOT NULL DEFAULT 0,

    allowed_ips     INET[],

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tokens_org_id
    ON ibex_core.tokens(org_id)
    WHERE is_revoked = FALSE;

CREATE INDEX idx_tokens_user_id
    ON ibex_core.tokens(user_id)
    WHERE user_id IS NOT NULL AND is_revoked = FALSE;

CREATE INDEX idx_tokens_hash
    ON ibex_core.tokens(hash);

CREATE TRIGGER tokens_updated_at
    BEFORE UPDATE ON ibex_core.tokens
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
