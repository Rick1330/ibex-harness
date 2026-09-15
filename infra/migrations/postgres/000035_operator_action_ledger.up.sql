-- Milestone 4.P.1 decision 10: operator action ledger (schema + dual-approval hooks).

CREATE TABLE ibex_core.operator_action_ledger (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id                  UUID NOT NULL
                            REFERENCES ibex_core.organizations(id)
                            ON DELETE CASCADE,
    actor_user_id           UUID NOT NULL,
    action                  TEXT NOT NULL,
    resource_type           TEXT,
    resource_id             TEXT,
    preview_token           TEXT NOT NULL,
    step_up_jti             TEXT,
    requires_second_actor   BOOLEAN NOT NULL DEFAULT FALSE,
    second_actor_user_id    UUID,
    second_actor_at         TIMESTAMPTZ,
    idempotency_key         TEXT NOT NULL,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, idempotency_key)
);

CREATE INDEX idx_operator_action_ledger_org_created
    ON ibex_core.operator_action_ledger (org_id, created_at DESC);

ALTER TABLE ibex_core.operator_action_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.operator_action_ledger FORCE ROW LEVEL SECURITY;

CREATE POLICY operator_action_ledger_isolation ON ibex_core.operator_action_ledger
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.operator_action_ledger TO ibex_app;
