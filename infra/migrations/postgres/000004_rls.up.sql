ALTER TABLE ibex_core.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.organizations FORCE ROW LEVEL SECURITY;

CREATE POLICY organizations_isolation ON ibex_core.organizations
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

ALTER TABLE ibex_core.tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.tokens FORCE ROW LEVEL SECURITY;

CREATE POLICY tokens_isolation ON ibex_core.tokens
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_app') THEN
        CREATE ROLE ibex_app NOLOGIN;
    END IF;
END
$$;

GRANT ibex_app TO ibex;

GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.organizations TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.tokens TO ibex_app;
