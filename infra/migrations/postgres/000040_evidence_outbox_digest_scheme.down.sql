-- Restore the legacy digest contract before removing the per-row scheme marker.
UPDATE ibex_core.evidence_outbox
SET payload_digest = encode(sha256(convert_to(payload::text, 'UTF8')), 'hex')
WHERE payload_digest_scheme = 'jcs/v1';

DROP FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER);

ALTER FUNCTION ibex_core.evidence_outbox_claim_pending_legacy(INTEGER)
    RENAME TO evidence_outbox_claim_pending;

ALTER TABLE ibex_core.evidence_outbox
    DROP COLUMN payload_digest_scheme;

GRANT EXECUTE ON FUNCTION ibex_core.evidence_outbox_claim_pending(INTEGER)
    TO ibex_evidence_relay;
