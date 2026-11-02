-- Companion to 000055: the deletion-evidence fence count is
-- `memories WHERE org_id = ? AND tombstoned`. Partial, because tombstoned rows
-- are the minority and the predicate is the whole point.
-- Separate file so CONCURRENTLY is never wrapped in the implicit transaction.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_org_tombstoned
    ON ibex_core.memories (org_id)
    WHERE tombstoned;
