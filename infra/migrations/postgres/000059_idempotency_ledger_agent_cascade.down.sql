-- CONCURRENTLY for the same reason as the up migration (single statement).
DROP INDEX CONCURRENTLY IF EXISTS ibex_core.idx_idempotency_ledger_agent_id;
