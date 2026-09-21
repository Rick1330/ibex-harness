-- Milestone 4.P.1: durable per-org model-policy epoch (F4-016).

CREATE TABLE ibex_core.org_model_policy_meta (
    org_id     UUID PRIMARY KEY
               REFERENCES ibex_core.organizations(id)
               ON DELETE CASCADE,
    epoch      BIGINT NOT NULL DEFAULT 1
               CHECK (epoch >= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO ibex_core.org_model_policy_meta (org_id, epoch)
SELECT DISTINCT org_id, 1
FROM ibex_core.org_model_policies
ON CONFLICT (org_id) DO NOTHING;

ALTER TABLE ibex_core.org_model_policy_meta ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.org_model_policy_meta FORCE ROW LEVEL SECURITY;

CREATE POLICY org_model_policy_meta_isolation ON ibex_core.org_model_policy_meta
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.org_model_policy_meta TO ibex_app;

CREATE TRIGGER org_model_policy_meta_updated_at
    BEFORE UPDATE ON ibex_core.org_model_policy_meta
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
