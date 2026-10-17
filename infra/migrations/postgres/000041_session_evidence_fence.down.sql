DROP TRIGGER IF EXISTS sessions_evidence_fence ON ibex_core.sessions;
DROP FUNCTION IF EXISTS ibex_core.advance_session_evidence_fence();
ALTER TABLE ibex_core.sessions
    DROP CONSTRAINT IF EXISTS sessions_evidence_fence_version_positive,
    DROP COLUMN IF EXISTS evidence_fence_version;
