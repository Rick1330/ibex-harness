ALTER TABLE ibex_core.evidence_outbox
    ADD COLUMN payload_digest_scheme TEXT NOT NULL
        DEFAULT 'postgres-jsonb-text/v1'
        CONSTRAINT evidence_outbox_payload_digest_scheme_check
        CHECK (payload_digest_scheme IN ('postgres-jsonb-text/v1', 'jcs/v1'));

-- The relay must receive the scheme from the SECURITY DEFINER claim function;
-- it does not get direct SELECT access to the tenant-scoped outbox table.
DROP FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER);

CREATE FUNCTION ibex_core.evidence_outbox_claim_pending(p_limit INTEGER)
RETURNS TABLE (
    id UUID,
    org_id UUID,
    event_id UUID,
    aggregate_id TEXT,
    aggregate_seq BIGINT,
    schema_version TEXT,
    event_type TEXT,
    payload JSONB,
    payload_digest TEXT,
    payload_digest_scheme TEXT,
    delivery_status TEXT,
    attempts INTEGER,
    available_at TIMESTAMPTZ,
    last_error TEXT,
    created_at TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 256 THEN
        RAISE EXCEPTION 'evidence_outbox_claim_pending: p_limit must be between 1 and 256';
    END IF;
    RETURN QUERY
    UPDATE ibex_core.evidence_outbox o
    SET delivery_status = 'in_flight',
        attempts = o.attempts + 1,
        claimed_at = NOW()
    WHERE o.id IN (
        SELECT e.id FROM ibex_core.evidence_outbox e
        WHERE e.delivery_status IN ('pending', 'failed')
          AND e.available_at <= NOW()
        ORDER BY e.available_at, e.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT p_limit
    )
    RETURNING
        o.id, o.org_id, o.event_id, o.aggregate_id, o.aggregate_seq,
        o.schema_version, o.event_type, o.payload, o.payload_digest,
        o.payload_digest_scheme, o.delivery_status, o.attempts, o.available_at,
        COALESCE(o.last_error, ''), o.created_at, o.delivered_at;
END;
$$;

ALTER FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER) FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER) FROM ibex_app;
GRANT EXECUTE ON FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER) TO ibex_evidence_relay;
