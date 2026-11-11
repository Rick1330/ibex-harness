-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Drops the unique prefix index. The advisory-lock + EXISTS guard in 000069's
-- bootstrap_upsert_service_token survives, so the bootstrap path keeps refusing
-- a cross-organization prefix; what goes away is the structural guarantee for
-- every other writer.
--
-- Single statement for CONCURRENTLY, like the up.
DROP INDEX CONCURRENTLY IF EXISTS ibex_core.idx_tokens_prefix_unique;
