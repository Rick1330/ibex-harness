-- Milestone 3.C.2 / ADR-0055: exact dedup uniqueness for active memories.
-- Partial unique on (org_id, agent_id, content_hash) among live active rows.
-- Soft-deleted / non-active rows may reuse the same hash after supersession (3.C.3).
-- CONCURRENTLY: same pattern as 000011 (golang-migrate ExecContext has no tx wrap).
-- Caveat: a failed CONCURRENTLY build can leave an INVALID index; DROP and retry.

CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_org_agent_content_hash_active
    ON ibex_core.memories (org_id, agent_id, content_hash)
    WHERE status = 'active' AND deleted_at IS NULL; -- NOSONAR
