-- Milestone 4.P.4: ibex_billing schema — rate cards, budget periods, enforcement decisions.
-- Usage event facts live in ClickHouse ibex.usage_facts (no TTL; billing retention).
-- Org deletion must NOT cascade-erase these tables (SECURITY.md §11 billing carve-out).

CREATE SCHEMA IF NOT EXISTS ibex_billing;

GRANT USAGE ON SCHEMA ibex_billing TO ibex_app;
GRANT USAGE ON SCHEMA ibex_billing TO ibex_service;

-- ================================================================
-- rate_cards (org-scoped catalog; versions are immutable once published)
-- ================================================================
CREATE TABLE ibex_billing.rate_cards (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    name            TEXT NOT NULL,
    currency        TEXT NOT NULL DEFAULT 'USD'
                    CHECK (char_length(currency) BETWEEN 3 AND 8),
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'published', 'archived')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT rate_cards_org_name_unique UNIQUE (org_id, name),
    CONSTRAINT rate_cards_id_org_unique UNIQUE (id, org_id)
);

CREATE INDEX idx_rate_cards_org_id ON ibex_billing.rate_cards (org_id);

CREATE TABLE ibex_billing.rate_card_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    rate_card_id    UUID NOT NULL,
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    version         BIGINT NOT NULL CHECK (version >= 1),
    published_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Prices: [{provider, model_pattern, input_cents_per_1k, output_cents_per_1k}, ...]
    prices          JSONB NOT NULL DEFAULT '[]'::jsonb,
    CONSTRAINT rate_card_versions_unique UNIQUE (rate_card_id, version),
    CONSTRAINT rate_card_versions_card_org_fk
        FOREIGN KEY (rate_card_id, org_id)
        REFERENCES ibex_billing.rate_cards (id, org_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_rate_card_versions_org_id ON ibex_billing.rate_card_versions (org_id);
CREATE INDEX idx_rate_card_versions_card ON ibex_billing.rate_card_versions (rate_card_id, version DESC);

-- ================================================================
-- budget_periods
-- ================================================================
CREATE TABLE ibex_billing.budget_periods (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE RESTRICT,
    period_start        TIMESTAMPTZ NOT NULL,
    period_end          TIMESTAMPTZ NOT NULL,
    cap_cents           BIGINT NOT NULL CHECK (cap_cents >= 0),
    spent_cents_cached  BIGINT NOT NULL DEFAULT 0 CHECK (spent_cents_cached >= 0),
    enforcement_mode    TEXT NOT NULL DEFAULT 'alert_only'
                        CHECK (enforcement_mode IN ('alert_only', 'hard_cap')),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT budget_periods_window CHECK (period_end > period_start),
    CONSTRAINT budget_periods_id_org_unique UNIQUE (id, org_id)
);

CREATE INDEX idx_budget_periods_org_window
    ON ibex_billing.budget_periods (org_id, period_start, period_end);

-- ================================================================
-- enforcement_decisions (audit trail for allow/deny/unavailable)
-- ================================================================
CREATE TABLE ibex_billing.enforcement_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    budget_period_id UUID,
    decision        TEXT NOT NULL
                    CHECK (decision IN ('allow', 'deny', 'unavailable')),
    reason          TEXT NOT NULL DEFAULT '',
    request_id      TEXT,
    remaining_cents BIGINT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT enforcement_decisions_period_org_fk
        FOREIGN KEY (budget_period_id, org_id)
        REFERENCES ibex_billing.budget_periods (id, org_id)
        -- MATCH SIMPLE: NULL budget_period_id skips the FK. Composite ON DELETE SET NULL
        -- would also null org_id (NOT NULL), so period clears run via trigger below.
);

CREATE INDEX idx_enforcement_decisions_org_created
    ON ibex_billing.enforcement_decisions (org_id, created_at DESC);

-- Preserve org_id on enforcement_decisions when a budget period is deleted.
-- SECURITY DEFINER owned by ibex_service (BYPASSRLS): clear without app UPDATE grants.
CREATE OR REPLACE FUNCTION ibex_billing.clear_enforcement_budget_period_id()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_billing, pg_temp
AS $$
BEGIN
    UPDATE ibex_billing.enforcement_decisions
    SET budget_period_id = NULL
    WHERE org_id = OLD.org_id
      AND budget_period_id = OLD.id;
    RETURN OLD;
END;
$$;

ALTER FUNCTION ibex_billing.clear_enforcement_budget_period_id() OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_billing.clear_enforcement_budget_period_id() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ibex_billing.clear_enforcement_budget_period_id() TO ibex_app;
GRANT EXECUTE ON FUNCTION ibex_billing.clear_enforcement_budget_period_id() TO ibex_service;

CREATE TRIGGER budget_periods_clear_enforcement_period_id
    BEFORE DELETE ON ibex_billing.budget_periods
    FOR EACH ROW EXECUTE FUNCTION ibex_billing.clear_enforcement_budget_period_id();

-- ================================================================
-- RLS
-- ================================================================
ALTER TABLE ibex_billing.rate_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.rate_cards FORCE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.rate_card_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.rate_card_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.budget_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.budget_periods FORCE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.enforcement_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_billing.enforcement_decisions FORCE ROW LEVEL SECURITY;

CREATE POLICY rate_cards_isolation ON ibex_billing.rate_cards
    USING (ibex_core.rls_org_visible(org_id));

CREATE POLICY rate_card_versions_isolation ON ibex_billing.rate_card_versions
    USING (ibex_core.rls_org_visible(org_id));

CREATE POLICY budget_periods_isolation ON ibex_billing.budget_periods
    USING (ibex_core.rls_org_visible(org_id));

CREATE POLICY enforcement_decisions_isolation ON ibex_billing.enforcement_decisions
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_billing.rate_cards TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_billing.rate_cards TO ibex_service;
GRANT SELECT, INSERT ON ibex_billing.rate_card_versions TO ibex_app;
GRANT SELECT, INSERT ON ibex_billing.rate_card_versions TO ibex_service;
-- Versions are immutable: no UPDATE/DELETE for app; service may SELECT/INSERT only.
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_billing.budget_periods TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_billing.budget_periods TO ibex_service;
GRANT SELECT, INSERT ON ibex_billing.enforcement_decisions TO ibex_app;
GRANT SELECT, INSERT ON ibex_billing.enforcement_decisions TO ibex_service;
-- Column UPDATE only for DEFINER owner (ibex_service); ibex_app cannot clear period IDs.
GRANT UPDATE (budget_period_id) ON ibex_billing.enforcement_decisions TO ibex_service;

CREATE TRIGGER rate_cards_updated_at
    BEFORE UPDATE ON ibex_billing.rate_cards
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

CREATE TRIGGER budget_periods_updated_at
    BEFORE UPDATE ON ibex_billing.budget_periods
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
