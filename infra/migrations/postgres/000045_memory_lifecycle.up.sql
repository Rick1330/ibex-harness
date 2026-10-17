-- GAP-007 provisional memory lifecycle substrate (not an accepted contract).
-- Existing rows start at lifecycle revision 1; deleted rows are reconciled to tombstones.
ALTER TABLE ibex_core.memories
    ADD COLUMN lifecycle_revision BIGINT NOT NULL DEFAULT 1 CHECK (lifecycle_revision > 0),
    ADD COLUMN tombstoned BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN expires_at TIMESTAMPTZ;

UPDATE ibex_core.memories
SET tombstoned = TRUE
WHERE status = 'deleted' OR deleted_at IS NOT NULL;

ALTER TABLE ibex_core.sessions
    ADD COLUMN lifecycle_revision BIGINT NOT NULL DEFAULT 1 CHECK (lifecycle_revision > 0);

CREATE OR REPLACE FUNCTION ibex_core.bump_session_lifecycle_revision()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF NEW.status IS DISTINCT FROM OLD.status
       OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
       OR NEW.org_id IS DISTINCT FROM OLD.org_id
       OR NEW.agent_id IS DISTINCT FROM OLD.agent_id THEN
        NEW.lifecycle_revision := OLD.lifecycle_revision + 1;
    ELSIF NEW.lifecycle_revision IS DISTINCT FROM OLD.lifecycle_revision THEN
        -- Memory forget advances the source session fence to invalidate queued writes.
        NEW.lifecycle_revision := OLD.lifecycle_revision + 1;
    ELSE
        -- Do not allow callers to forge the revision independently of lifecycle state.
        NEW.lifecycle_revision := OLD.lifecycle_revision;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION ibex_core.bump_session_lifecycle_revision() FROM PUBLIC;
CREATE TRIGGER sessions_bump_lifecycle_revision
    BEFORE UPDATE ON ibex_core.sessions
    FOR EACH ROW EXECUTE FUNCTION ibex_core.bump_session_lifecycle_revision();

CREATE OR REPLACE FUNCTION ibex_core.bump_memory_lifecycle_revision()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF OLD.tombstoned AND NOT NEW.tombstoned THEN
        RAISE EXCEPTION 'memory tombstone is terminal';
    END IF;
    IF NEW.status IS DISTINCT FROM OLD.status
       OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
       OR NEW.tombstoned IS DISTINCT FROM OLD.tombstoned
       OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
       OR NEW.valid_from IS DISTINCT FROM OLD.valid_from
       OR NEW.valid_until IS DISTINCT FROM OLD.valid_until
       OR NEW.superseded_by IS DISTINCT FROM OLD.superseded_by
       OR NEW.merged_into IS DISTINCT FROM OLD.merged_into
       OR NEW.content IS DISTINCT FROM OLD.content
       OR NEW.content_hash IS DISTINCT FROM OLD.content_hash
       OR NEW.content_tokens IS DISTINCT FROM OLD.content_tokens
       OR NEW.category IS DISTINCT FROM OLD.category
       OR NEW.confidence IS DISTINCT FROM OLD.confidence
       OR NEW.source IS DISTINCT FROM OLD.source
       OR NEW.metadata IS DISTINCT FROM OLD.metadata
       OR NEW.pii_detected IS DISTINCT FROM OLD.pii_detected
       OR NEW.pii_redacted IS DISTINCT FROM OLD.pii_redacted
       OR NEW.org_id IS DISTINCT FROM OLD.org_id
       OR NEW.agent_id IS DISTINCT FROM OLD.agent_id THEN
        NEW.lifecycle_revision := OLD.lifecycle_revision + 1;
    ELSE
        -- Index, score, and feedback updates cannot forge or advance lifecycle state.
        NEW.lifecycle_revision := OLD.lifecycle_revision;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION ibex_core.bump_memory_lifecycle_revision() FROM PUBLIC;
CREATE TRIGGER memories_bump_lifecycle_revision
    BEFORE UPDATE ON ibex_core.memories
    FOR EACH ROW EXECUTE FUNCTION ibex_core.bump_memory_lifecycle_revision();

CREATE TABLE ibex_core.memory_lifecycle_outbox (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Intentionally not FK-cascaded: purge events must survive organization row cleanup.
    org_id UUID NOT NULL,
    memory_id UUID NOT NULL,
    revision BIGINT NOT NULL CHECK (revision > 0),
    schema_version SMALLINT NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    event_type TEXT NOT NULL CHECK (event_type IN (
        'created', 'quarantined', 'content_updated', 'superseded', 'forgotten', 'expired', 'purged'
    )),
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_until TIMESTAMPTZ,
    delivered_at TIMESTAMPTZ,
    UNIQUE (org_id, memory_id, revision)
);

CREATE INDEX idx_memory_lifecycle_outbox_pending
    ON ibex_core.memory_lifecycle_outbox (available_at, occurred_at, id)
    WHERE delivered_at IS NULL;

ALTER TABLE ibex_core.memory_lifecycle_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_lifecycle_outbox FORCE ROW LEVEL SECURITY;
CREATE POLICY memory_lifecycle_outbox_isolation
    ON ibex_core.memory_lifecycle_outbox
    USING (ibex_core.rls_org_visible(org_id))
    WITH CHECK (ibex_core.rls_org_visible(org_id));

-- The memory application inserts/reads its tenant's outbox rows. The service role
-- may lease/ack rows for a future dedicated lifecycle relay. The existing evidence
-- outbox is not reused: it is keyed to run requests, not memory lifecycle revisions.
GRANT SELECT, INSERT ON ibex_core.memory_lifecycle_outbox TO ibex_app;
GRANT SELECT, INSERT, UPDATE ON ibex_core.memory_lifecycle_outbox TO ibex_service;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_service;

COMMENT ON TABLE ibex_core.memory_lifecycle_outbox IS
    'Provisional redacted memory lifecycle events; payload is normalized columns only; one event per org/memory/revision.';
COMMENT ON COLUMN ibex_core.memories.lifecycle_revision IS
    'Monotonic lifecycle revision; advanced by database trigger on lifecycle state changes.';
COMMENT ON COLUMN ibex_core.memories.tombstoned IS
    'Terminal visibility fence; tombstones win in all retrieval modes.';
COMMENT ON COLUMN ibex_core.sessions.lifecycle_revision IS
    'Monotonic session lifecycle fence advanced on eligibility changes and session-linked memory forget.';

-- The deletion saga persists hold_blocked and never reclaims that terminal state.
-- The original status check omitted this value, making legal-hold deferral fail at commit.
ALTER TABLE ibex_core.org_deletion_jobs
    DROP CONSTRAINT org_deletion_jobs_status_check;
ALTER TABLE ibex_core.org_deletion_jobs
    ADD CONSTRAINT org_deletion_jobs_status_check
    CHECK (status IN ('pending', 'running', 'succeeded', 'failed', 'hold_blocked'));
