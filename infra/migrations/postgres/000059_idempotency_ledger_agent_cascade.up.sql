-- W3 tenancy and erasure: let the idempotency ledger follow its agent instead
-- of aborting the organization-deletion saga.
--
-- `idempotency_ledger.agent_id` was NO ACTION, so `DELETE FROM agents` raised a
-- foreign-key violation and the job could never reach `succeeded` (P0-07). The
-- sibling agent tables (tokens, sessions, rate_limit_overrides,
-- budget_reservations) already cascade.
ALTER TABLE ibex_core.idempotency_ledger
    DROP CONSTRAINT IF EXISTS idempotency_ledger_agent_id_fkey;
ALTER TABLE ibex_core.idempotency_ledger
    ADD CONSTRAINT idempotency_ledger_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES ibex_core.agents(id) ON DELETE CASCADE;
