-- Revert the idempotency-ledger cascade.
DROP INDEX IF EXISTS ibex_core.idx_idempotency_ledger_agent_id;
ALTER TABLE ibex_core.idempotency_ledger
    DROP CONSTRAINT IF EXISTS idempotency_ledger_agent_id_fkey;
ALTER TABLE ibex_core.idempotency_ledger
    ADD CONSTRAINT idempotency_ledger_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES ibex_core.agents(id);
