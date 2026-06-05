CREATE TABLE ibex_core.users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    email           TEXT NOT NULL,
    name            TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member'
                    CHECK (role IN ('owner', 'admin', 'member', 'viewer')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'invited', 'suspended', 'deactivated')),

    -- SSO (nullable; filled when org uses SSO)
    sso_provider    TEXT,
    sso_subject     TEXT,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    UNIQUE(org_id, email),
    CONSTRAINT users_email_format CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$')
);

CREATE INDEX idx_users_org_id
    ON ibex_core.users(org_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_users_email
    ON ibex_core.users(email)
    WHERE deleted_at IS NULL;

ALTER TABLE ibex_core.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.users FORCE ROW LEVEL SECURITY;

CREATE POLICY users_isolation ON ibex_core.users
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR (
            id = NULLIF(current_setting('app.current_user_id', true), '')::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.users TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON ibex_core.users
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

