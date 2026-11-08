-- Restore the original NO ACTION constraint (000043).
ALTER TABLE ibex_core.idempotency_ledger
    DROP CONSTRAINT IF EXISTS idempotency_ledger_agent_id_fkey;
ALTER TABLE ibex_core.idempotency_ledger
    ADD CONSTRAINT idempotency_ledger_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES ibex_core.agents(id);
