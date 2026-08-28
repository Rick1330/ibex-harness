-- Milestone 3.C.5 / ADR-0057: durable conflict escalations for ESCALATE_PENDING outcomes.
-- CREATE (not expand): table did not exist prior to this migration.
-- Composite org-scoped FKs match memory_relationships (000016) and memory_labels (000015).

CREATE TABLE ibex_core.memory_conflict_escalations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE RESTRICT,
    new_memory_id       UUID NOT NULL,
    candidate_memory_id UUID NOT NULL,
    conflict_type       TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN (
                            'pending', -- NOSONAR
                            'resolved',
                            'dismissed'
                        )),
    subject_key         TEXT,
    reason              TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,
    resolved_by         UUID,

    CONSTRAINT memory_conflict_escalations_new_memory_org_fk
        FOREIGN KEY (new_memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE,

    CONSTRAINT memory_conflict_escalations_candidate_org_fk
        FOREIGN KEY (candidate_memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE,

    CONSTRAINT memory_conflict_escalations_distinct_memories_chk
        CHECK (new_memory_id <> candidate_memory_id)
);

-- Worker poll: pending escalations per org, newest first.
CREATE INDEX idx_memory_conflict_escalations_org_status_pending
    ON ibex_core.memory_conflict_escalations (org_id, created_at DESC)
    WHERE status = 'pending'; -- NOSONAR

ALTER TABLE ibex_core.memory_conflict_escalations ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_conflict_escalations FORCE ROW LEVEL SECURITY;

CREATE POLICY memory_conflict_escalations_isolation
    ON ibex_core.memory_conflict_escalations
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.memory_conflict_escalations TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
