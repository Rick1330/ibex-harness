-- 000047: authoritative session tombstone/version fence check for the evidence
-- relay daemon (GAP-011 PR3).
--
-- SECURITY DEFINER helper owned by ibex_service (BYPASSRLS, NOLOGIN).
-- EXECUTE is granted only to ibex_evidence_relay — never ibex_app, which must
-- not read cross-tenant lifecycle rows through this helper.
--
-- The relay daemon connects with a login DSN whose role is a member of
-- ibex_evidence_relay (deployment prerequisite) and calls this function for
-- each claimed outbox row whose tombstone fence is a session resource.
-- Outcomes: 'alive' | 'tombstoned' | 'stale_version' | 'not_found'.
-- Missing rows, deleted rows, and version mismatches fail closed at the caller.
CREATE OR REPLACE FUNCTION ibex_core.evidence_outbox_check_session_fence(
    p_org_id UUID,
    p_resource_id UUID,
    p_resource_ver BIGINT
)
RETURNS TEXT
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_deleted_at TIMESTAMPTZ;
    v_fence BIGINT;
BEGIN
    IF p_org_id IS NULL OR p_resource_id IS NULL OR p_resource_ver IS NULL OR p_resource_ver <= 0 THEN
        RAISE EXCEPTION 'evidence_outbox_check_session_fence: invalid parameters';
    END IF;

    SELECT s.deleted_at, s.evidence_fence_version
    INTO v_deleted_at, v_fence
    FROM ibex_core.sessions s
    WHERE s.org_id = p_org_id
      AND s.id = p_resource_id;

    IF NOT FOUND THEN
        RETURN 'not_found';
    END IF;

    -- Tombstones take precedence over version drift: a soft-deleted session
    -- also advanced its fence version, and the terminal decision is tombstoned.
    IF v_deleted_at IS NOT NULL THEN
        RETURN 'tombstoned';
    END IF;

    IF v_fence <> p_resource_ver THEN
        RETURN 'stale_version';
    END IF;

    RETURN 'alive';
END;
$$;

-- The SECURITY DEFINER owner needs SELECT on the four lifecycle columns this
-- helper reads. Column-level grant keeps ibex_service's surface minimal:
-- function execution requires table privileges on top of BYPASSRLS.
GRANT SELECT (id, org_id, deleted_at, evidence_fence_version)
    ON ibex_core.sessions TO ibex_service;

ALTER FUNCTION ibex_core.evidence_outbox_check_session_fence(UUID, UUID, BIGINT) OWNER TO ibex_service;

REVOKE ALL ON FUNCTION ibex_core.evidence_outbox_check_session_fence(UUID, UUID, BIGINT) FROM PUBLIC;

REVOKE EXECUTE ON FUNCTION ibex_core.evidence_outbox_check_session_fence(UUID, UUID, BIGINT) FROM ibex_app;

GRANT EXECUTE ON FUNCTION ibex_core.evidence_outbox_check_session_fence(UUID, UUID, BIGINT) TO ibex_evidence_relay;
