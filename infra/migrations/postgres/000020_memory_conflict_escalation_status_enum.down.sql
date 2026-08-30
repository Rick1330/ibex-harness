-- Dev/test rollback only. Production is forward-only (ADR-0005).

DROP INDEX IF EXISTS idx_memory_conflict_escalations_org_status_pending;

ALTER TABLE ibex_core.memory_conflict_escalations
    ALTER COLUMN status DROP DEFAULT;

ALTER TABLE ibex_core.memory_conflict_escalations
    ALTER COLUMN status TYPE TEXT
    USING status::text;

ALTER TABLE ibex_core.memory_conflict_escalations
    ADD CONSTRAINT memory_conflict_escalations_status_check
    CHECK (status IN (
        'pending', -- NOSONAR
        'resolved',
        'dismissed'
    ));

ALTER TABLE ibex_core.memory_conflict_escalations
    ALTER COLUMN status SET DEFAULT 'pending';

CREATE INDEX idx_memory_conflict_escalations_org_status_pending
    ON ibex_core.memory_conflict_escalations (org_id, created_at DESC)
    WHERE status = 'pending'; -- NOSONAR

DROP TYPE IF EXISTS ibex_core.memory_conflict_escalation_status;
