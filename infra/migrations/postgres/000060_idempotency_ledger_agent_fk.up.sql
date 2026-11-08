-- W3 tenancy and erasure: let the idempotency ledger follow its agent instead
-- of aborting the organization-deletion saga (P0-07).
--
-- `idempotency_ledger.agent_id` was NO ACTION, so `DELETE FROM agents` raised a
-- foreign-key violation and the job could never reach `succeeded`. The sibling
-- agent tables (tokens, sessions, rate_limit_overrides, budget_reservations)
-- already cascade.
--
-- NOT VALID takes only a brief ACCESS EXCLUSIVE catalog lock and does not scan
-- the table. The validation is 000061, deliberately a separate migration: one
-- file is one implicit transaction, so validating here would hold the
-- replacement's lock for the whole scan. Between this and 000061 the constraint
-- is enforced for new rows and trusted by nothing.
ALTER TABLE ibex_core.idempotency_ledger
    DROP CONSTRAINT IF EXISTS idempotency_ledger_agent_id_fkey;
ALTER TABLE ibex_core.idempotency_ledger
    ADD CONSTRAINT idempotency_ledger_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES ibex_core.agents(id) ON DELETE CASCADE NOT VALID;
