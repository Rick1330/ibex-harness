-- Milestone 4.C.2: per-org model allow/deny policies (proxy gate + management CRUD).
-- fallback_chain is intentionally omitted until 4.C.4 has a real consumer (ADR-0075).

CREATE TABLE ibex_core.org_model_policies (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         UUID NOT NULL
                   REFERENCES ibex_core.organizations(id)
                   ON DELETE CASCADE,
    model_pattern  TEXT NOT NULL
                   CHECK (char_length(model_pattern) BETWEEN 1 AND 256),
    allowed        BOOLEAN NOT NULL,
    priority       INTEGER NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT org_model_policies_org_pattern_unique UNIQUE (org_id, model_pattern)
);

CREATE INDEX idx_org_model_policies_org_priority
    ON ibex_core.org_model_policies (org_id, priority ASC);

ALTER TABLE ibex_core.org_model_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.org_model_policies FORCE ROW LEVEL SECURITY;

CREATE POLICY org_model_policies_isolation ON ibex_core.org_model_policies
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.org_model_policies TO ibex_app;

CREATE TRIGGER org_model_policies_updated_at
    BEFORE UPDATE ON ibex_core.org_model_policies
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
