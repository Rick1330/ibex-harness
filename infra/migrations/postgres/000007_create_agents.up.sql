CREATE TABLE ibex_core.agents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL
                REFERENCES ibex_core.organizations(id)
                ON DELETE RESTRICT,
    created_by  UUID
                REFERENCES ibex_core.users(id)
                ON DELETE SET NULL,
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL,

    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'paused', 'suspended', 'archived')),
    config      JSONB NOT NULL DEFAULT '{}',
    metadata    JSONB NOT NULL DEFAULT '{}',
    tags        TEXT[] NOT NULL DEFAULT '{}',

    -- Statistics (denormalized; maintained by triggers in later phases)
    total_sessions    INTEGER NOT NULL DEFAULT 0,
    total_memories    INTEGER NOT NULL DEFAULT 0,
    total_tokens_used BIGINT  NOT NULL DEFAULT 0,
    last_active_at    TIMESTAMPTZ,

    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at  TIMESTAMPTZ,

    UNIQUE(org_id, slug),
    CONSTRAINT agents_slug_format CHECK (slug ~ '^[a-z0-9-]+$')
);

CREATE INDEX idx_agents_org_id
    ON ibex_core.agents(org_id)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_agents_status
    ON ibex_core.agents(org_id, status)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_agents_tags
    ON ibex_core.agents USING gin(tags)
    WHERE deleted_at IS NULL;

ALTER TABLE ibex_core.agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.agents FORCE ROW LEVEL SECURITY;

CREATE POLICY agents_isolation ON ibex_core.agents
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

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.agents TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE TRIGGER agents_updated_at
    BEFORE UPDATE ON ibex_core.agents
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

