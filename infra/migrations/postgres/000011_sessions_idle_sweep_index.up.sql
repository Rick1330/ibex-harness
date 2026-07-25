-- Partial index for idle-session sweeper scans (m2.4.4).
CREATE INDEX idx_sessions_active_updated_at
    ON ibex_core.sessions (updated_at)
    WHERE status = 'active' AND deleted_at IS NULL;
