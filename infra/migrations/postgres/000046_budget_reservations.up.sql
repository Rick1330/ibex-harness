-- budget-reservation.v1 (provisional, implemented-local): durable admission
-- holds behind the existing hard_cap enforcement. A reservation exists only
-- while the organization has an active hard_cap budget period; organizations
-- without hard caps keep the cache-only middleware behavior and create no rows.
-- finalized rows are the durable audit record; release/expire keep the history
-- (rows are never deleted by the application roles; agent deletion cascades as
-- the table owner during organization teardown, like the sibling agent tables).
-- price_* columns capture the matched rate at claim time so worker settlement
-- and idempotent replay never depend on the currently published rate card. The
-- Go proxy settles with explicit measured amounts and leaves them NULL; keys
-- are service-namespaced so only the owning service settles a row.
CREATE TABLE ibex_core.budget_reservations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES ibex_core.organizations(id),
    agent_id UUID NOT NULL REFERENCES ibex_core.agents(id) ON DELETE CASCADE,
    budget_period_id UUID NOT NULL REFERENCES ibex_billing.budget_periods(id),
    reservation_key TEXT NOT NULL CHECK (char_length(reservation_key) BETWEEN 1 AND 256),
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL CHECK (state IN ('claimed', 'finalized', 'released', 'expired')),
    amount_estimated_cents BIGINT NOT NULL CHECK (amount_estimated_cents >= 0),
    price_input_cents_per_1k INTEGER CHECK (price_input_cents_per_1k IS NULL OR price_input_cents_per_1k >= 0),
    price_output_cents_per_1k INTEGER CHECK (price_output_cents_per_1k IS NULL OR price_output_cents_per_1k >= 0),
    amount_final_cents BIGINT CHECK (amount_final_cents >= 0),
    finalized_completeness TEXT CHECK (finalized_completeness IN ('complete', 'estimated')),
    lease_expires_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, agent_id, reservation_key),
    CHECK ((state = 'finalized' AND amount_final_cents IS NOT NULL AND finalized_completeness IS NOT NULL)
        OR (state <> 'finalized' AND amount_final_cents IS NULL AND finalized_completeness IS NULL)),
    CHECK ((state = 'claimed' AND lease_expires_at IS NOT NULL)
        OR (state <> 'claimed' AND lease_expires_at IS NULL)),
    CHECK (lease_expires_at IS NULL OR lease_expires_at > created_at)
);
CREATE INDEX idx_budget_reservations_active
    ON ibex_core.budget_reservations (organization_id, budget_period_id)
    WHERE state = 'claimed';
CREATE INDEX idx_budget_reservations_lease
    ON ibex_core.budget_reservations (lease_expires_at)
    WHERE state = 'claimed';
ALTER TABLE ibex_core.budget_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.budget_reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY budget_reservations_isolation ON ibex_core.budget_reservations
    USING (ibex_core.rls_org_visible(organization_id));
-- No DELETE: rows are the durable accounting record; the reaper runs with the
-- service-account GUC (rls_org_visible) and only transitions state.
GRANT SELECT, INSERT, UPDATE ON ibex_core.budget_reservations TO ibex_app;
GRANT SELECT, INSERT, UPDATE ON ibex_core.budget_reservations TO ibex_service;
COMMENT ON TABLE ibex_core.budget_reservations IS 'budget-reservation.v1 durable admission holds for hard_cap organizations; scoped to org + agent + reservation key';
