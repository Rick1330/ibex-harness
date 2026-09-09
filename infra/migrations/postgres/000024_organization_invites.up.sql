-- Organization invitation tokens (hashed; raw token returned once at create).
CREATE TABLE ibex_core.organization_invites (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,
    email           TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member'
                    CHECK (role IN ('admin', 'member', 'viewer')),
    token_hash      TEXT NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    used_at         TIMESTAMPTZ,
    created_by      UUID REFERENCES ibex_core.users(id) ON DELETE SET NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT organization_invites_email_format
        CHECK (email ~ '^[^@]+@[^@]+\.[^@]+$')
);

CREATE UNIQUE INDEX idx_organization_invites_token_hash
    ON ibex_core.organization_invites(token_hash);

CREATE INDEX idx_organization_invites_org_email
    ON ibex_core.organization_invites(org_id, email)
    WHERE used_at IS NULL;

ALTER TABLE ibex_core.organization_invites ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.organization_invites FORCE ROW LEVEL SECURITY;

CREATE POLICY organization_invites_isolation ON ibex_core.organization_invites
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.organization_invites TO ibex_app;
