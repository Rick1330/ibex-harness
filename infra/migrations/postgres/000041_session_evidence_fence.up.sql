-- Evidence fence for the existing session lifecycle row; no parallel lifecycle table is introduced.
-- Session ownership stays in packages/session/PostgreSQL. The version advances atomically
-- with the first soft-delete transition and cannot be set or rolled back by application SQL.
ALTER TABLE ibex_core.sessions
    ADD COLUMN evidence_fence_version BIGINT NOT NULL DEFAULT 1,
    ADD CONSTRAINT sessions_evidence_fence_version_positive
        CHECK (evidence_fence_version > 0);

COMMENT ON COLUMN ibex_core.sessions.evidence_fence_version IS
    'Monotonic evidence lifecycle fence; advanced by the PostgreSQL session soft-delete trigger.';

CREATE OR REPLACE FUNCTION ibex_core.advance_session_evidence_fence()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        NEW.evidence_fence_version := OLD.evidence_fence_version + 1;
    ELSIF OLD.deleted_at IS NOT NULL AND NEW.deleted_at IS NULL THEN
        RAISE EXCEPTION 'session tombstones cannot be cleared';
    ELSIF NEW.evidence_fence_version IS DISTINCT FROM OLD.evidence_fence_version THEN
        RAISE EXCEPTION 'session evidence fence is managed by lifecycle trigger';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION ibex_core.advance_session_evidence_fence() FROM PUBLIC;

CREATE TRIGGER sessions_evidence_fence
    BEFORE UPDATE OF deleted_at, evidence_fence_version ON ibex_core.sessions
    FOR EACH ROW EXECUTE FUNCTION ibex_core.advance_session_evidence_fence();
