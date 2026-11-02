-- Companion to 000053: per-version usage is "sessions for these version ids in a
-- window". The existing partial index leads with directive_version_id alone, so
-- the window filter cannot use it. Separate file so CONCURRENTLY is not wrapped.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sessions_org_directive_created
    ON ibex_core.sessions (org_id, directive_version_id, created_at DESC)
    WHERE directive_version_id IS NOT NULL;
