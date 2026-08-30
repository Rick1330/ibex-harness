-- Follow-up to 000019: replace TEXT status + CHECK with a typed enum (Sonar S1192).
-- Safe for databases already at schema version 19+.

DROP INDEX IF EXISTS idx_memory_conflict_escalations_org_status_pending;

CREATE TYPE ibex_core.memory_conflict_escalation_status AS ENUM (
    'pending',
    'resolved',
    'dismissed'
);

ALTER TABLE ibex_core.memory_conflict_escalations
    ALTER COLUMN status DROP DEFAULT;

ALTER TABLE ibex_core.memory_conflict_escalations
    DROP CONSTRAINT IF EXISTS memory_conflict_escalations_status_check;

ALTER TABLE ibex_core.memory_conflict_escalations
    ALTER COLUMN status TYPE ibex_core.memory_conflict_escalation_status
    USING status::text::ibex_core.memory_conflict_escalation_status;

ALTER TABLE ibex_core.memory_conflict_escalations
    ALTER COLUMN status SET DEFAULT 'pending'::ibex_core.memory_conflict_escalation_status;

CREATE INDEX idx_memory_conflict_escalations_org_status_pending
    ON ibex_core.memory_conflict_escalations (org_id, created_at DESC)
    WHERE status = 'pending'::ibex_core.memory_conflict_escalation_status;
