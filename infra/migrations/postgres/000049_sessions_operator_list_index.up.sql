-- Operator session list: keyset page over (created_at DESC, id DESC) within an org,
-- excluding logically deleted sessions.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_org_created_at
    ON ibex_core.sessions (org_id, created_at DESC, id DESC)
    WHERE deleted_at IS NULL;
