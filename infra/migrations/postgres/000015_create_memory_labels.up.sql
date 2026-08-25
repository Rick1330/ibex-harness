-- Milestone 2.5.G5.M2: multi-label memory_labels join table.
-- Phase 3 naming (memory_labels), not sketch memory_categories — see ADR-0048.
-- Keep memories.category as derived primary when labels exist.

CREATE TABLE ibex_core.memory_labels (
    memory_id   UUID NOT NULL,
    org_id      UUID NOT NULL
                REFERENCES ibex_core.organizations(id)
                ON DELETE RESTRICT,
    label       TEXT NOT NULL
                CHECK (label IN (
                    'factual',
                    'preference',
                    'behavioral',
                    'episodic',
                    'procedural'
                )),
    confidence  NUMERIC(3,2) NOT NULL DEFAULT 1.00
                CHECK (confidence >= 0 AND confidence <= 1),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (memory_id, label),

    CONSTRAINT memory_labels_memory_org_fk
        FOREIGN KEY (memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_memory_labels_org_label
    ON ibex_core.memory_labels (org_id, label);

-- Sync memories.category from highest-confidence label (tie: label ASC).
-- When no labels remain, leave category unchanged (NOT NULL).
CREATE OR REPLACE FUNCTION ibex_core.sync_memory_primary_category()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    target_memory_id UUID;
    target_org_id UUID;
    primary_label TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        target_memory_id := OLD.memory_id;
        target_org_id := OLD.org_id;
    ELSE
        target_memory_id := NEW.memory_id;
        target_org_id := NEW.org_id;
    END IF;

    SELECT ml.label INTO primary_label
    FROM ibex_core.memory_labels ml
    WHERE ml.memory_id = target_memory_id
      AND ml.org_id = target_org_id
    ORDER BY ml.confidence DESC, ml.label ASC
    LIMIT 1;

    IF primary_label IS NOT NULL THEN
        UPDATE ibex_core.memories
        SET category = primary_label
        WHERE id = target_memory_id
          AND org_id = target_org_id
          AND category IS DISTINCT FROM primary_label;
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION ibex_core.sync_memory_primary_category() FROM PUBLIC;

CREATE TRIGGER memory_labels_sync_primary_category
    AFTER INSERT OR UPDATE OR DELETE ON ibex_core.memory_labels
    FOR EACH ROW EXECUTE FUNCTION ibex_core.sync_memory_primary_category();

-- Backfill one label per existing memory from scalar category.
INSERT INTO ibex_core.memory_labels (memory_id, org_id, label, confidence)
SELECT id, org_id, category, 1.00
FROM ibex_core.memories
ON CONFLICT DO NOTHING;

ALTER TABLE ibex_core.memory_labels ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_labels FORCE ROW LEVEL SECURITY;

CREATE POLICY memory_labels_isolation ON ibex_core.memory_labels
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.memory_labels TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
