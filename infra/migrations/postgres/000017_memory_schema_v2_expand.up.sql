-- Milestone 3.1.1 / ADR-0052: expand ibex_core.memories with pgvector embedding,
-- HNSW, quality columns, and hybrid-search tsvector.
-- EXPAND only — do NOT CREATE memories / memory_labels / memory_relationships
-- (those shipped in 000014–000016 / ADR-0047–0049).
-- Keep observed_at and memories.category (primary-category rename deferred).

-- ADR-0005 deferred CREATE EXTENSION vector until memory schema needed it;
-- ADR-0047 lifted that deferral to this expand. Requires pgvector-capable image
-- (compose-dev/test and CI use pgvector/pgvector:pg16).
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE ibex_core.memories
    ADD COLUMN embedding vector(1024),
    ADD COLUMN embedding_model TEXT,
    ADD COLUMN embedding_dim INTEGER,
    ADD COLUMN confidence NUMERIC(3,2) NOT NULL DEFAULT 0.80,
    ADD COLUMN usefulness_score NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    ADD COLUMN source TEXT NOT NULL DEFAULT 'extracted',
    ADD COLUMN superseded_by UUID,
    ADD COLUMN merged_into UUID,
    ADD COLUMN retrieval_count INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN last_retrieved_at TIMESTAMPTZ,
    ADD COLUMN pii_detected BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN pii_redacted BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Embedding triplet: all NULL, or embedding set with model + dim=1024 (bge-m3).
ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_embedding_triplet_chk
    CHECK (
        (embedding IS NULL AND embedding_model IS NULL AND embedding_dim IS NULL)
        OR (
            embedding IS NOT NULL
            AND embedding_model IS NOT NULL
            AND length(embedding_model) > 0
            AND embedding_dim = 1024
        )
    );

ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_confidence_range_chk
    CHECK (confidence >= 0 AND confidence <= 1);

ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_usefulness_range_chk
    CHECK (usefulness_score >= 0 AND usefulness_score <= 1);

ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_source_chk
    CHECK (source IN ('extracted', 'user_provided', 'imported', 'inferred'));

ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_retrieval_count_nonneg_chk
    CHECK (retrieval_count >= 0);

-- Composite org-safe FKs (MATCH SIMPLE: NULL tip skips the check).
ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_superseded_by_org_fk
    FOREIGN KEY (superseded_by, org_id)
    REFERENCES ibex_core.memories (id, org_id);

ALTER TABLE ibex_core.memories
    ADD CONSTRAINT memories_merged_into_org_fk
    FOREIGN KEY (merged_into, org_id)
    REFERENCES ibex_core.memories (id, org_id);

-- Hybrid-search fallback (Track D). Generated columns cannot subquery other tables.
ALTER TABLE ibex_core.memories
    ADD COLUMN search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(content, '')), 'A')
    ) STORED;

-- HNSW: pgvector documented defaults (m=16, ef_construction=64). Non-CONCURRENTLY:
-- table has no product write traffic yet (DEPLOYMENT.md §8.1 Rule B = large tables).
-- Future index adds under write load must use CREATE INDEX CONCURRENTLY (see 000011).
CREATE INDEX idx_memories_embedding_hnsw
    ON ibex_core.memories
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE status = 'active' AND deleted_at IS NULL; -- NOSONAR

-- Temporal-interval lookup for Track C conflict detection.
CREATE INDEX idx_memories_validity
    ON ibex_core.memories (org_id, agent_id, valid_from, valid_until)
    WHERE status = 'active' AND deleted_at IS NULL; -- NOSONAR

CREATE INDEX idx_memories_search_vector
    ON ibex_core.memories USING GIN (search_vector)
    WHERE status = 'active' AND deleted_at IS NULL; -- NOSONAR

-- Hidden mutation (already shipped in 000015 — do not re-CREATE):
-- Trigger memory_labels_sync_primary_category / function sync_memory_primary_category
-- writes memories.category = highest-confidence label (ORDER BY confidence DESC, label ASC).
-- Logical name is "primary category"; physical rename category → primary_category is deferred
-- (ADR-0052). RLS on memory_labels remains rls_org_visible(org_id) — never subquery memories.
