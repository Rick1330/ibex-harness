-- Operator memory list: keyset page over (created_at DESC, id DESC) within an org.
-- CONCURRENTLY: golang-migrate postgres Run() uses ExecContext (no tx wrap); one
-- concurrent index per file so the implicit multi-statement transaction never wraps it.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_org_created_at
    ON ibex_core.memories (org_id, created_at DESC, id DESC);
