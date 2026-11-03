-- Companion to 000051: the summary's delivery block filters the outbox by org and
-- outbox row age. Separate file because CONCURRENTLY cannot run inside the
-- implicit transaction a multi-statement file would create.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_evidence_outbox_org_created_at
    ON ibex_core.evidence_outbox (org_id, created_at DESC);
