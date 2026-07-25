-- Partial index for idle-session sweeper scans (m2.4.4).
-- CONCURRENTLY: golang-migrate postgres Run() uses ExecContext (no tx wrap).
-- Caveat: a failed CONCURRENTLY build can leave an INVALID index; DROP and retry.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_active_updated_at
    ON ibex_core.sessions (updated_at)
    WHERE status = 'active' AND deleted_at IS NULL;
