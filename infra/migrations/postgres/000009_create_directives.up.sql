-- Milestone 2.3.1: agent directive config + immutable version history.
-- Phase 2 subset (see ADR-0030). Full marketplace-oriented schema in
-- DATABASE_SCHEMA.md remains deferred.

-- Enables composite FK (agent_id, org_id) → agents(id, org_id).
ALTER TABLE ibex_core.agents
    ADD CONSTRAINT agents_id_org_unique UNIQUE (id, org_id);

CREATE TABLE ibex_core.directives (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id            UUID NOT NULL
                      REFERENCES ibex_core.organizations(id)
                      ON DELETE CASCADE,
    agent_id          UUID NOT NULL,
    active_version_id UUID,
    injection_mode    TEXT NOT NULL DEFAULT 'system_first'
                      CHECK (injection_mode IN ('system_first', 'system_append', 'user_prepend')),
    is_active         BOOLEAN NOT NULL DEFAULT true,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (agent_id),
    UNIQUE (id, org_id),
    CONSTRAINT directives_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE
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
    UNIQUE (id, org_id),
    UNIQUE (id, directive_id),
    CONSTRAINT directive_versions_content_not_empty CHECK (length(content) > 0),
    CONSTRAINT directive_versions_content_max CHECK (octet_length(content) <= 32768),
    CONSTRAINT directive_versions_directive_org_fk
        FOREIGN KEY (directive_id, org_id)
        REFERENCES ibex_core.directives (id, org_id)
        ON DELETE CASCADE
);

ALTER TABLE ibex_core.directives
    ADD CONSTRAINT directives_active_version_org_fk
    FOREIGN KEY (active_version_id, org_id)
    REFERENCES ibex_core.directive_versions (id, org_id)
    ON DELETE SET NULL (active_version_id)
    NOT VALID;

ALTER TABLE ibex_core.directives
    ADD CONSTRAINT directives_active_version_directive_fk
    FOREIGN KEY (active_version_id, id)
    REFERENCES ibex_core.directive_versions (id, directive_id)
    ON DELETE SET NULL (active_version_id)
    NOT VALID;

ALTER TABLE ibex_core.directives VALIDATE CONSTRAINT directives_active_version_org_fk;
ALTER TABLE ibex_core.directives VALIDATE CONSTRAINT directives_active_version_directive_fk;

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
-- Append-only versions: no UPDATE (DELETE retained for parent CASCADE cleanup).
GRANT SELECT, INSERT, DELETE ON ibex_core.directive_versions TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE OR REPLACE FUNCTION ibex_core.reject_directive_version_update()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'directive_versions is append-only';
END;
$$;

CREATE TRIGGER directive_versions_immutable
    BEFORE UPDATE ON ibex_core.directive_versions
    FOR EACH ROW EXECUTE FUNCTION ibex_core.reject_directive_version_update();

CREATE TRIGGER directives_updated_at
    BEFORE UPDATE ON ibex_core.directives
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
