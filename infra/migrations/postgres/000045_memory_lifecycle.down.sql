-- Rollback is safe only before lifecycle events have been consumed or used as authority.
-- Once published, lifecycle history is not reconstructible; do not run this down migration
-- after a consumer has acted on outbox rows without an explicit recovery plan.
DO $$
BEGIN
    PERFORM set_config('app.is_service_account', 'true', true);
    IF EXISTS (SELECT 1 FROM ibex_core.memory_lifecycle_outbox)
       OR EXISTS (SELECT 1 FROM ibex_core.org_deletion_jobs WHERE status = 'hold_blocked')
       OR EXISTS (
           SELECT 1 FROM ibex_core.memories
           WHERE tombstoned = TRUE OR lifecycle_revision > 1 OR expires_at IS NOT NULL
       )
       OR EXISTS (
           SELECT 1 FROM ibex_core.sessions WHERE lifecycle_revision > 1
       ) THEN
        RAISE EXCEPTION 'refusing destructive 000045 rollback after lifecycle state/events exist';
    END IF;
END;
$$;

ALTER TABLE ibex_core.org_deletion_jobs
    DROP CONSTRAINT org_deletion_jobs_status_check;
ALTER TABLE ibex_core.org_deletion_jobs
    ADD CONSTRAINT org_deletion_jobs_status_check
    CHECK (status IN ('pending', 'running', 'succeeded', 'failed'));

DROP TABLE ibex_core.memory_lifecycle_outbox;

DROP TRIGGER memories_bump_lifecycle_revision ON ibex_core.memories;
DROP FUNCTION ibex_core.bump_memory_lifecycle_revision();
DROP TRIGGER sessions_bump_lifecycle_revision ON ibex_core.sessions;
DROP FUNCTION ibex_core.bump_session_lifecycle_revision();

ALTER TABLE ibex_core.memories
    DROP COLUMN expires_at,
    DROP COLUMN tombstoned,
    DROP COLUMN lifecycle_revision;
ALTER TABLE ibex_core.sessions
    DROP COLUMN lifecycle_revision;
