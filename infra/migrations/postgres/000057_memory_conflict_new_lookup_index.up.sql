-- Companion to 000019 / ADR-0094: the read path resolves the pending conflict
-- escalations a hydrated memory belongs to, from the "new memory" side.
-- The existing (org_id, created_at DESC) partial index serves the worker poll,
-- not this lookup. Partial, because only pending escalations are read.
-- CONCURRENTLY: golang-migrate postgres Run() uses ExecContext (no tx wrap); one
-- concurrent index per file so the implicit multi-statement transaction never wraps it.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memory_conflict_escalations_org_new_pending
    ON ibex_core.memory_conflict_escalations (org_id, new_memory_id)
    WHERE status = 'pending'; -- NOSONAR
