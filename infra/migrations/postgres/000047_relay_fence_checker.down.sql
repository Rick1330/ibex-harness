-- 000047 down: remove the evidence relay session-fence checker.
REVOKE EXECUTE ON FUNCTION ibex_core.evidence_outbox_check_session_fence(UUID, UUID, BIGINT) FROM ibex_evidence_relay;

REVOKE SELECT (id, org_id, deleted_at, evidence_fence_version)
    ON ibex_core.sessions FROM ibex_service;

DROP FUNCTION IF EXISTS ibex_core.evidence_outbox_check_session_fence(UUID, UUID, BIGINT);
