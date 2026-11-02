-- Deletion evidence: the tombstones block filters lifecycle events by org and
-- window, and the fence count filters tombstoned memories by org. The existing
-- lifecycle index serves the relay lease path (available_at, undelivered), not
-- this one, and `memories` has no partial tombstone index.
-- CONCURRENTLY, one index per file body, matching 000048-000054.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memory_lifecycle_outbox_org_occurred
    ON ibex_core.memory_lifecycle_outbox (org_id, occurred_at DESC);
