-- Milestone 4.P.3: privacy audit ledger, legal holds, capture policies,
-- deletion store receipts, hold_blocked job status, hash-chain append helper.
--
-- Non-erasable allowlist (saga MUST refuse to delete these store names):
--   today: none (placeholder for future usage/billing ledgers — 4.P.4).
-- Audit ledger has NO FK to organizations so rows survive org soft-delete.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ================================================================
-- org_deletion_jobs: add hold_blocked status
-- ================================================================
ALTER TABLE ibex_core.org_deletion_jobs
    DROP CONSTRAINT IF EXISTS org_deletion_jobs_status_check;

ALTER TABLE ibex_core.org_deletion_jobs
    ADD CONSTRAINT org_deletion_jobs_status_check
    CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'hold_blocked'));

-- ================================================================
-- privacy_audit_ledger (append-only, org_id survives purge)
-- ================================================================
CREATE TABLE ibex_core.privacy_audit_ledger (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL,  -- NO FK: survives org soft-delete / purge
    seq                 BIGINT NOT NULL,
    prev_hash           TEXT NOT NULL,
    row_hash            TEXT NOT NULL,
    actor_user_id       UUID,
    action              TEXT NOT NULL
                        CHECK (char_length(action) BETWEEN 1 AND 128),
    purpose             TEXT
                        CHECK (purpose IS NULL OR char_length(purpose) <= 512),
    policy_result       TEXT
                        CHECK (policy_result IS NULL OR char_length(policy_result) <= 128),
    object_type         TEXT
                        CHECK (object_type IS NULL OR char_length(object_type) <= 128),
    object_id           TEXT
                        CHECK (object_id IS NULL OR char_length(object_id) <= 256),
    fields              TEXT[] NOT NULL DEFAULT '{}',
    approval_ref        TEXT
                        CHECK (approval_ref IS NULL OR char_length(approval_ref) <= 256),
    before_hash         TEXT,
    after_hash          TEXT,
    correlation_id      TEXT
                        CHECK (correlation_id IS NULL OR char_length(correlation_id) <= 128),
    request_id          TEXT
                        CHECK (request_id IS NULL OR char_length(request_id) <= 128),
    payload             JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, seq)
);

CREATE INDEX idx_privacy_audit_ledger_org_seq
    ON ibex_core.privacy_audit_ledger (org_id, seq DESC);

ALTER TABLE ibex_core.privacy_audit_ledger ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.privacy_audit_ledger FORCE ROW LEVEL SECURITY;

CREATE POLICY privacy_audit_ledger_isolation ON ibex_core.privacy_audit_ledger
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

-- Append-only: no UPDATE/DELETE; INSERT only via privacy_audit_append (SECURITY DEFINER).
REVOKE ALL ON TABLE ibex_core.privacy_audit_ledger FROM PUBLIC;
REVOKE UPDATE, DELETE, INSERT ON ibex_core.privacy_audit_ledger FROM ibex_app;
GRANT SELECT ON ibex_core.privacy_audit_ledger TO ibex_app;
GRANT SELECT, INSERT ON ibex_core.privacy_audit_ledger TO ibex_service;

CREATE OR REPLACE FUNCTION ibex_core.privacy_audit_ledger_forbid_mutate()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'privacy_audit_ledger is append-only';
END;
$$;

CREATE TRIGGER privacy_audit_ledger_no_update_delete
    BEFORE UPDATE OR DELETE ON ibex_core.privacy_audit_ledger
    FOR EACH ROW EXECUTE FUNCTION ibex_core.privacy_audit_ledger_forbid_mutate();

-- ================================================================
-- privacy_audit_append (SECURITY DEFINER / ibex_service)
-- Canonical serialization (fixed column order; jsonb keys sorted):
--   org_id|seq|prev_hash|actor_user_id|action|purpose|policy_result|
--   object_type|object_id|fields(csv sorted)|approval_ref|before_hash|
--   after_hash|correlation_id|request_id|payload_canonical|created_at_rfc3339nano
-- row_hash = encode(digest(canonical, 'sha256'), 'hex')
-- Genesis prev_hash = 64 zero hex chars.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.privacy_audit_append(
    p_org_id            UUID,
    p_actor_user_id     UUID,
    p_action            TEXT,
    p_purpose           TEXT,
    p_policy_result     TEXT,
    p_object_type       TEXT,
    p_object_id         TEXT,
    p_fields            TEXT[],
    p_approval_ref      TEXT,
    p_before_hash       TEXT,
    p_after_hash        TEXT,
    p_correlation_id    TEXT,
    p_request_id        TEXT,
    p_payload           JSONB
)
RETURNS TABLE (
    id UUID,
    org_id UUID,
    seq BIGINT,
    prev_hash TEXT,
    row_hash TEXT,
    created_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_prev              TEXT;
    v_seq               BIGINT;
    v_fields_sorted     TEXT[];
    v_payload_canon     TEXT;
    v_created           TIMESTAMPTZ := clock_timestamp();
    v_canonical         TEXT;
    v_row_hash          TEXT;
    v_id                UUID := gen_random_uuid();
    v_genesis           TEXT := repeat('0', 64);
BEGIN
    IF p_org_id IS NULL THEN
        RAISE EXCEPTION 'privacy_audit_append: org_id required';
    END IF;
    IF p_action IS NULL OR char_length(p_action) < 1 OR char_length(p_action) > 128 THEN
        RAISE EXCEPTION 'privacy_audit_append: action invalid';
    END IF;

    -- Serialize appends per org within the transaction.
    PERFORM pg_advisory_xact_lock(hashtext(p_org_id::text));

    SELECT l.row_hash, l.seq
      INTO v_prev, v_seq
      FROM ibex_core.privacy_audit_ledger l
     WHERE l.org_id = p_org_id
     ORDER BY l.seq DESC
     LIMIT 1;

    IF v_seq IS NULL THEN
        v_seq := 1;
        v_prev := v_genesis;
    ELSE
        v_seq := v_seq + 1;
    END IF;

    IF p_fields IS NULL OR array_length(p_fields, 1) IS NULL THEN
        v_fields_sorted := ARRAY[]::TEXT[];
    ELSE
        SELECT COALESCE(array_agg(x ORDER BY x), ARRAY[]::TEXT[])
          INTO v_fields_sorted
          FROM unnest(p_fields) AS x;
    END IF;

    v_payload_canon := COALESCE(p_payload, '{}'::jsonb)::text;

    v_canonical := concat_ws(
        '|',
        p_org_id::text,
        v_seq::text,
        v_prev,
        COALESCE(p_actor_user_id::text, ''),
        p_action,
        COALESCE(p_purpose, ''),
        COALESCE(p_policy_result, ''),
        COALESCE(p_object_type, ''),
        COALESCE(p_object_id, ''),
        COALESCE(array_to_string(v_fields_sorted, ','), ''),
        COALESCE(p_approval_ref, ''),
        COALESCE(p_before_hash, ''),
        COALESCE(p_after_hash, ''),
        COALESCE(p_correlation_id, ''),
        COALESCE(p_request_id, ''),
        v_payload_canon,
        to_char(v_created AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"')
    );

    v_row_hash := encode(digest(v_canonical, 'sha256'), 'hex');

    INSERT INTO ibex_core.privacy_audit_ledger (
        id, org_id, seq, prev_hash, row_hash,
        actor_user_id, action, purpose, policy_result,
        object_type, object_id, fields, approval_ref,
        before_hash, after_hash, correlation_id, request_id,
        payload, created_at
    ) VALUES (
        v_id, p_org_id, v_seq, v_prev, v_row_hash,
        p_actor_user_id, p_action, p_purpose, p_policy_result,
        p_object_type, p_object_id, v_fields_sorted, p_approval_ref,
        p_before_hash, p_after_hash, p_correlation_id, p_request_id,
        COALESCE(p_payload, '{}'::jsonb), v_created
    );

    RETURN QUERY SELECT v_id, p_org_id, v_seq, v_prev, v_row_hash, v_created;
END;
$$;

ALTER FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) OWNER TO ibex_service;

REVOKE ALL ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM ibex_app;
-- Worker/API run as ibex_app with is_service_account GUC; grant EXECUTE to
-- ibex_app so service-account sessions can append (RLS still applies on SELECT).
-- Direct INSERT remains available; forge-resistant chaining requires this helper.
GRANT EXECUTE ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) TO ibex_app;
GRANT EXECUTE ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) TO ibex_service;

-- ================================================================
-- legal_holds
-- ================================================================
CREATE TABLE ibex_core.legal_holds (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE RESTRICT,
    scope           TEXT NOT NULL DEFAULT 'org'
                    CHECK (char_length(scope) BETWEEN 1 AND 128),
    reason          TEXT NOT NULL
                    CHECK (char_length(reason) BETWEEN 1 AND 1024),
    set_by          UUID NOT NULL,
    cleared_by      UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at      TIMESTAMPTZ
);

CREATE INDEX idx_legal_holds_org_active
    ON ibex_core.legal_holds (org_id)
    WHERE cleared_at IS NULL;

ALTER TABLE ibex_core.legal_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.legal_holds FORCE ROW LEVEL SECURITY;

CREATE POLICY legal_holds_isolation ON ibex_core.legal_holds
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.legal_holds TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.legal_holds TO ibex_service;

-- ================================================================
-- org_capture_policies (priority load like org_model_policies)
-- ================================================================
CREATE TABLE ibex_core.org_capture_policies (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL
                    REFERENCES ibex_core.organizations(id)
                    ON DELETE CASCADE,
    agent_id        UUID,
    mode            TEXT NOT NULL
                    CHECK (mode IN ('none', 'metadata_only', 'redacted', 'full')),
    priority        INTEGER NOT NULL DEFAULT 100,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT org_capture_policies_org_agent_unique
        UNIQUE NULLS NOT DISTINCT (org_id, agent_id)
);

CREATE INDEX idx_org_capture_policies_org_priority
    ON ibex_core.org_capture_policies (org_id, priority ASC);

ALTER TABLE ibex_core.org_capture_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.org_capture_policies FORCE ROW LEVEL SECURITY;

CREATE POLICY org_capture_policies_isolation ON ibex_core.org_capture_policies
    USING (
        (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND org_id = current_setting('app.current_org_id', true)::UUID
        )
        OR current_setting('app.is_service_account', true) = 'true'
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.org_capture_policies TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.org_capture_policies TO ibex_service;

CREATE TRIGGER org_capture_policies_updated_at
    BEFORE UPDATE ON ibex_core.org_capture_policies
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

-- ================================================================
-- deletion_store_receipts
-- ================================================================
CREATE TABLE ibex_core.deletion_store_receipts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID NOT NULL
                        REFERENCES ibex_core.org_deletion_jobs(id)
                        ON DELETE CASCADE,
    store               TEXT NOT NULL
                        CHECK (store IN ('postgres', 'clickhouse', 'redis', 'objectstore')),
    scope               TEXT NOT NULL DEFAULT 'org'
                        CHECK (char_length(scope) BETWEEN 1 AND 256),
    status              TEXT NOT NULL
                        CHECK (status IN ('pending', 'verified', 'failed')),
    verified_absent_at  TIMESTAMPTZ,
    idempotency_key     TEXT NOT NULL
                        CHECK (char_length(idempotency_key) BETWEEN 1 AND 256),
    error               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (job_id, store, idempotency_key)
);

CREATE INDEX idx_deletion_store_receipts_job
    ON ibex_core.deletion_store_receipts (job_id, store);

ALTER TABLE ibex_core.deletion_store_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.deletion_store_receipts FORCE ROW LEVEL SECURITY;

-- Receipts inherit org visibility via join to org_deletion_jobs under service GUC,
-- or via job org when app.current_org_id is set.
CREATE POLICY deletion_store_receipts_isolation ON ibex_core.deletion_store_receipts
    USING (
        current_setting('app.is_service_account', true) = 'true'
        OR (
            NULLIF(current_setting('app.current_org_id', true), '') IS NOT NULL
            AND EXISTS (
                SELECT 1 FROM ibex_core.org_deletion_jobs j
                WHERE j.id = deletion_store_receipts.job_id
                  AND j.org_id = current_setting('app.current_org_id', true)::UUID
            )
        )
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.deletion_store_receipts TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.deletion_store_receipts TO ibex_service;

CREATE TRIGGER deletion_store_receipts_updated_at
    BEFORE UPDATE ON ibex_core.deletion_store_receipts
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();
