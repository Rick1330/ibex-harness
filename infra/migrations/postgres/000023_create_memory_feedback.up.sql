-- Milestone 3.5.E.3: memory_feedback ledger for usefulness scoring.
-- One vote per (org_id, memory_id, agent_id); upsert replaces prior vote.
-- Composite org-scoped FKs match memory_labels / memory_conflict_escalations.

CREATE TABLE ibex_core.memory_feedback (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id      UUID NOT NULL
                REFERENCES ibex_core.organizations(id)
                ON DELETE RESTRICT,
    memory_id   UUID NOT NULL,
    agent_id    UUID NOT NULL,
    feedback    TEXT NOT NULL
                CHECK (feedback IN (
                    'positive', -- NOSONAR
                    'negative',
                    'neutral'
                )),
    session_id  UUID,
    trace_id    UUID,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT memory_feedback_org_memory_agent_uq
        UNIQUE (org_id, memory_id, agent_id),

    CONSTRAINT memory_feedback_memory_org_fk
        FOREIGN KEY (memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE,

    CONSTRAINT memory_feedback_agent_org_fk
        FOREIGN KEY (agent_id, org_id)
        REFERENCES ibex_core.agents (id, org_id)
        ON DELETE CASCADE,

    CONSTRAINT memory_feedback_notes_max_chk
        CHECK (notes IS NULL OR octet_length(notes) <= 2000)
);

CREATE INDEX idx_memory_feedback_org_memory
    ON ibex_core.memory_feedback (org_id, memory_id);

ALTER TABLE ibex_core.memory_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_feedback FORCE ROW LEVEL SECURITY;

CREATE POLICY memory_feedback_isolation
    ON ibex_core.memory_feedback
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.memory_feedback TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

CREATE TRIGGER memory_feedback_updated_at
    BEFORE UPDATE ON ibex_core.memory_feedback
    FOR EACH ROW
    EXECUTE FUNCTION ibex_core.set_updated_at();
