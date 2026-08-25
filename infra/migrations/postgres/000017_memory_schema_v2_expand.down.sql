-- Dev/test only (ADR-0005: production is forward-only).
-- Leave the vector extension installed — other objects or future migrations may depend on it.

DROP INDEX IF EXISTS ibex_core.idx_memories_search_vector;
DROP INDEX IF EXISTS ibex_core.idx_memories_validity;
DROP INDEX IF EXISTS ibex_core.idx_memories_embedding_hnsw;

ALTER TABLE ibex_core.memories
    DROP COLUMN IF EXISTS search_vector;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_merged_into_org_fk;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_superseded_by_org_fk;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_retrieval_count_nonneg_chk;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_source_chk;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_usefulness_range_chk;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_confidence_range_chk;

ALTER TABLE ibex_core.memories
    DROP CONSTRAINT IF EXISTS memories_embedding_triplet_chk;

ALTER TABLE ibex_core.memories
    DROP COLUMN IF EXISTS metadata,
    DROP COLUMN IF EXISTS pii_redacted,
    DROP COLUMN IF EXISTS pii_detected,
    DROP COLUMN IF EXISTS last_retrieved_at,
    DROP COLUMN IF EXISTS retrieval_count,
    DROP COLUMN IF EXISTS merged_into,
    DROP COLUMN IF EXISTS superseded_by,
    DROP COLUMN IF EXISTS source,
    DROP COLUMN IF EXISTS usefulness_score,
    DROP COLUMN IF EXISTS confidence,
    DROP COLUMN IF EXISTS embedding_dim,
    DROP COLUMN IF EXISTS embedding_model,
    DROP COLUMN IF EXISTS embedding;
