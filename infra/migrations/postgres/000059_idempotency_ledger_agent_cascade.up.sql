-- W3 tenancy and erasure: index the cascading FK's lookup column.
--
-- The cascade's RI trigger looks rows up by agent_id, and no existing index has
-- it as a leading column (000043 creates only the lease index and the
-- (organization_id, agent_id, dedupe_key) unique index), so deleting an agent
-- would sequentially scan the whole ledger.
--
-- Single statement on purpose: golang-migrate sends one file through one
-- ExecContext, and a multi-statement string is an implicit transaction, in
-- which CREATE INDEX CONCURRENTLY is illegal. It is CONCURRENTLY so the build
-- does not block ledger writes; a failed build leaves an INVALID index — drop
-- and retry.
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_idempotency_ledger_agent_id
    ON ibex_core.idempotency_ledger (agent_id);
