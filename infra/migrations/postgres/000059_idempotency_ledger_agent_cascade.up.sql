-- W3 tenancy and erasure: let the idempotency ledger follow its agent instead
-- of aborting the organization-deletion saga.
--
-- `idempotency_ledger.agent_id` was NO ACTION, so `DELETE FROM agents` raised a
-- foreign-key violation and the job could never reach `succeeded` (P0-07). The
-- sibling agent tables (tokens, sessions, rate_limit_overrides,
-- budget_reservations) already cascade.
--
-- The cascade's RI trigger scans by agent_id, so index it; validate the
-- constraint separately to avoid holding a blocking lock for the whole table.
CREATE INDEX IF NOT EXISTS idx_idempotency_ledger_agent_id
    ON ibex_core.idempotency_ledger (agent_id);

ALTER TABLE ibex_core.idempotency_ledger
    DROP CONSTRAINT IF EXISTS idempotency_ledger_agent_id_fkey;
ALTER TABLE ibex_core.idempotency_ledger
    ADD CONSTRAINT idempotency_ledger_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES ibex_core.agents(id) ON DELETE CASCADE NOT VALID;
ALTER TABLE ibex_core.idempotency_ledger
    VALIDATE CONSTRAINT idempotency_ledger_agent_id_fkey;
