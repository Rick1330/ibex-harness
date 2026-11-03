-- request-idempotency-core.v1, bounded first slice: session termination admission.
CREATE TABLE ibex_core.idempotency_ledger (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID NOT NULL REFERENCES ibex_core.organizations(id),
    agent_id UUID NOT NULL REFERENCES ibex_core.agents(id),
    dedupe_key TEXT NOT NULL CHECK (char_length(dedupe_key) BETWEEN 1 AND 256),
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    state TEXT NOT NULL CHECK (state IN ('claimed', 'finalized', 'reconciling', 'failed_terminal')),
    status_code INTEGER,
    response_payload BYTEA,
    lease_expires_at TIMESTAMPTZ,
    version BIGINT NOT NULL DEFAULT 1 CHECK (version > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (organization_id, agent_id, dedupe_key),
    CHECK ((state = 'finalized' AND status_code IS NOT NULL AND response_payload IS NOT NULL)
        OR state <> 'finalized')
);
CREATE INDEX idx_idempotency_ledger_lease ON ibex_core.idempotency_ledger (lease_expires_at)
    WHERE state = 'claimed';
ALTER TABLE ibex_core.idempotency_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.idempotency_ledger FORCE ROW LEVEL SECURITY;
CREATE POLICY idempotency_ledger_isolation ON ibex_core.idempotency_ledger
    USING (organization_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE ON ibex_core.idempotency_ledger TO ibex_app;
GRANT SELECT, INSERT, UPDATE ON ibex_core.idempotency_ledger TO ibex_service;
COMMENT ON TABLE ibex_core.idempotency_ledger IS 'request-idempotency-core.v1 durable claim/finalize ledger; scoped to org + agent + key';
