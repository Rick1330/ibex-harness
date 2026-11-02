-- Operator evidence summary: every read is bounded by an org and a time window.
-- Without these, a 24h summary scans the organization's retained history because
-- the existing evidence indexes lead with trace/session/checkpoint/aggregate ids.
-- CONCURRENTLY: golang-migrate postgres Run() uses ExecContext (no tx wrap);
-- one index per file body so the implicit multi-statement transaction never wraps it.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_evidence_runs_org_started_at
    ON ibex_core.evidence_runs (org_id, started_at DESC);
