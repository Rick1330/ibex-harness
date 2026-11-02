-- Session detail: turn-to-trace join looks up the latest run for an org checkpoint.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_evidence_runs_org_checkpoint
    ON ibex_core.evidence_runs (org_id, checkpoint_id)
    WHERE checkpoint_id IS NOT NULL;
