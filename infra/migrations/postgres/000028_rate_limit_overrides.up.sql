-- Milestone 4.B.2: per-org / per-agent RPM overrides (management API + proxy reload).
CREATE TABLE ibex_core.rate_limit_overrides (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               UUID NOT NULL
                         REFERENCES ibex_core.organizations(id)
                         ON DELETE CASCADE,
    agent_id             UUID,
    requests_per_minute  INTEGER NOT NULL
                         CHECK (requests_per_minute >= 1),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Agent-scoped rows: one override per (org, agent).
    -- Org-level rows use agent_id IS NULL; NULLs are not unique under this
    -- constraint — see rate_limit_overrides_org_level_uidx.
    CONSTRAINT rate_limit_overrides_agent_unique UNIQUE (org_id, agent_id),
    CONSTRAINT rate_limit_overrides_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE
);

-- Exactly one org-level override row per organization.
CREATE UNIQUE INDEX rate_limit_overrides_org_level_uidx
    ON ibex_core.rate_limit_overrides (org_id)
    WHERE agent_id IS NULL;

CREATE INDEX idx_rate_limit_overrides_org_id
    ON ibex_core.rate_limit_overrides (org_id);

ALTER TABLE ibex_core.rate_limit_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.rate_limit_overrides FORCE ROW LEVEL SECURITY;

CREATE POLICY rate_limit_overrides_isolation ON ibex_core.rate_limit_overrides
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.rate_limit_overrides TO ibex_app;

CREATE TRIGGER rate_limit_overrides_updated_at
    BEFORE UPDATE ON ibex_core.rate_limit_overrides
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
