-- Milestone 2.3.1: agent directive config + immutable version history.
-- Phase 2 subset (see ADR-0030). Full marketplace-oriented schema in
-- DATABASE_SCHEMA.md remains deferred.

CREATE TABLE ibex_core.directives (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL
                      REFERENCES ibex_core.organizations(id)
                      ON DELETE CASCADE,
    agent_id          UUID NOT NULL
                      REFERENCES ibex_core.agents(id)
                      ON DELETE CASCADE,
    active_version_id UUID,
    injection_mode    TEXT NOT NULL DEFAULT 'system_first'
                      CHECK (injection_mode IN ('system_first', 'system_append', 'user_prepend')),
    is_active         BOOLEAN NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id),
    -- Supports composite FK from directive_versions so org_id cannot diverge.
    UNIQUE (id, org_id)
);

CREATE TABLE ibex_core.directive_versions (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    directive_id  UUID NOT NULL,
    org_id        UUID NOT NULL
                  REFERENCES ibex_core.organizations(id)
                  ON DELETE CASCADE,
    version_num   INTEGER NOT NULL,
    content       TEXT NOT NULL,
    content_hash  TEXT NOT NULL,
    created_by    UUID
                  REFERENCES ibex_core.users(id)
                  ON DELETE SET NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (directive_id, version_num),
    CONSTRAINT directive_versions_content_not_empty CHECK (length(content) > 0),
    CONSTRAINT directive_versions_content_max CHECK (length(content) <= 32768),
    CONSTRAINT directive_versions_directive_org_fk
        FOREIGN KEY (directive_id, org_id)
        REFERENCES ibex_core.directives (id, org_id)
        ON DELETE CASCADE
);

ALTER TABLE ibex_core.directives
    ADD CONSTRAINT directives_active_version_id_fk
    FOREIGN KEY (active_version_id)
    REFERENCES ibex_core.directive_versions(id)
    ON DELETE SET NULL
    NOT VALID;

ALTER TABLE ibex_core.directives VALIDATE CONSTRAINT directives_active_version_id_fk;

CREATE INDEX idx_directives_agent_id
    ON ibex_core.directives(agent_id)
    WHERE is_active = true;

CREATE INDEX idx_directive_versions_directive_id
    ON ibex_core.directive_versions(directive_id);

ALTER TABLE ibex_core.directives ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.directives FORCE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.directive_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.directive_versions FORCE ROW LEVEL SECURITY;

CREATE POLICY directives_isolation ON ibex_core.directives
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

CREATE POLICY directive_versions_isolation ON ibex_core.directive_versions
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.directives TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.directive_versions TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE TRIGGER directives_updated_at
    BEFORE UPDATE ON ibex_core.directives
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
