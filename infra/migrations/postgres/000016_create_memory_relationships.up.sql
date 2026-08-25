-- Milestone 2.5.G5.M3: memory_relationships graph foundation.
-- CREATE (not index-only ALTER): table did not exist prior to this migration.
-- Dual org-scoped traversal indexes + supersession view + tip helper — ADR-0049.

CREATE TABLE ibex_core.memory_relationships (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              UUID NOT NULL
                        REFERENCES ibex_core.organizations(id)
                        ON DELETE RESTRICT,
    source_memory_id    UUID NOT NULL,
    target_memory_id    UUID NOT NULL,
    relationship_type   TEXT NOT NULL
                        CHECK (relationship_type IN (
                            'supersedes',
                            'contradicts',
                            'specializes',
                            'generalizes',
                            'merged_from',
                            'derived_from'
                        )),
    confidence          NUMERIC(3,2) NOT NULL DEFAULT 0.90
                        CHECK (confidence >= 0 AND confidence <= 1),
    resolution_notes    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE (source_memory_id, target_memory_id, relationship_type),

    CONSTRAINT memory_relationships_no_self_loop_chk
        CHECK (source_memory_id <> target_memory_id),

    CONSTRAINT memory_relationships_source_org_fk
        FOREIGN KEY (source_memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE,

    CONSTRAINT memory_relationships_target_org_fk
        FOREIGN KEY (target_memory_id, org_id)
        REFERENCES ibex_core.memories (id, org_id)
        ON DELETE CASCADE
);

-- Forward walks: filter by source + type (what did this memory replace?).
CREATE INDEX idx_memory_relationships_org_source_type
    ON ibex_core.memory_relationships (org_id, source_memory_id, relationship_type);

-- Reverse walks: filter by target + type (resolve supersession tip).
CREATE INDEX idx_memory_relationships_org_target_type
    ON ibex_core.memory_relationships (org_id, target_memory_id, relationship_type);

ALTER TABLE ibex_core.memory_relationships ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_relationships FORCE ROW LEVEL SECURITY;

CREATE POLICY memory_relationships_isolation ON ibex_core.memory_relationships
    USING (ibex_core.rls_org_visible(org_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.memory_relationships TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;

-- Supersedes-only projection for recursive CTE base cases (caller RLS applies).
CREATE VIEW ibex_core.memory_supersession_edges
WITH (security_invoker = true) AS
SELECT
    id,
    org_id,
    source_memory_id,
    target_memory_id,
    confidence,
    resolution_notes,
    created_at
FROM ibex_core.memory_relationships
WHERE relationship_type = 'supersedes';

GRANT SELECT ON ibex_core.memory_supersession_edges TO ibex_app;

-- Walk incoming supersedes (target → source) to the current tip.
-- org_id at every level; depth cap; cycle break via path array.
CREATE OR REPLACE FUNCTION ibex_core.resolve_supersession_tip(
    p_org_id uuid,
    p_memory_id uuid,
    p_max_depth integer DEFAULT 5
)
RETURNS uuid
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    tip uuid;
    max_depth integer;
BEGIN
    max_depth := COALESCE(p_max_depth, 5);
    IF max_depth < 1 THEN
        RETURN p_memory_id;
    END IF;

    WITH RECURSIVE walk AS (
        SELECT
            p_memory_id AS mem_id,
            0 AS depth,
            ARRAY[p_memory_id]::uuid[] AS path
        UNION ALL
        SELECT
            e.source_memory_id,
            w.depth + 1,
            w.path || e.source_memory_id
        FROM walk w
        INNER JOIN ibex_core.memory_relationships e
            ON e.target_memory_id = w.mem_id
           AND e.org_id = p_org_id
           AND e.relationship_type = 'supersedes'
        WHERE w.depth < max_depth
          AND NOT (e.source_memory_id = ANY (w.path))
    )
    SELECT mem_id INTO tip
    FROM walk
    ORDER BY depth DESC, mem_id ASC
    LIMIT 1;

    RETURN tip;
END;
$$;

REVOKE ALL ON FUNCTION ibex_core.resolve_supersession_tip(uuid, uuid, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ibex_core.resolve_supersession_tip(uuid, uuid, integer) TO ibex_app;
