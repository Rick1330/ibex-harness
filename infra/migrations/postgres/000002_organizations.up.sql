CREATE TABLE ibex_core.organizations (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    tier            TEXT NOT NULL DEFAULT 'free'
                    CHECK (tier IN ('free', 'pro', 'enterprise')),
    status          TEXT NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'suspended',
                                      'cancelled', 'trial')),

    custom_token_quota_monthly    BIGINT,
    custom_memory_quota           BIGINT,
    custom_agent_quota            INTEGER,

    stripe_customer_id            TEXT UNIQUE,
    billing_email                 TEXT,
    billing_cycle_anchor          DATE,

    settings                      JSONB NOT NULL DEFAULT '{}',

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deleted_at      TIMESTAMPTZ,

    CONSTRAINT organizations_slug_format
        CHECK (slug ~ '^[a-z0-9-]+$')
);

CREATE INDEX idx_organizations_slug
    ON ibex_core.organizations(slug)
    WHERE deleted_at IS NULL;

CREATE INDEX idx_organizations_stripe
    ON ibex_core.organizations(stripe_customer_id)
    WHERE stripe_customer_id IS NOT NULL;

CREATE TRIGGER organizations_updated_at
    BEFORE UPDATE ON ibex_core.organizations
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
