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
-- 000059 builds its index CONCURRENTLY, which can leave the index present but
-- INVALID if the build was interrupted; the next `migrate up` would then skip it
-- because of IF NOT EXISTS and silently leave the cascade without its lookup
-- index. Refuse to continue and say how to repair it. (A missing index is not a
-- failure: the cascade still works, just with a sequential scan.)
DO $$
DECLARE index_valid boolean;
BEGIN
    SELECT i.indisvalid INTO index_valid
    FROM pg_index i
    WHERE i.indexrelid = to_regclass('ibex_core.idx_idempotency_ledger_agent_id');
    IF index_valid IS FALSE THEN
        RAISE EXCEPTION
            'idx_idempotency_ledger_agent_id is INVALID (interrupted CONCURRENTLY build). '
            'Repair with: DROP INDEX CONCURRENTLY ibex_core.idx_idempotency_ledger_agent_id; '
            'then re-run `migrate up`.';
    END IF;
END;
$$;

ALTER TABLE ibex_core.idempotency_ledger
    DROP CONSTRAINT IF EXISTS idempotency_ledger_agent_id_fkey;
ALTER TABLE ibex_core.idempotency_ledger
    ADD CONSTRAINT idempotency_ledger_agent_id_fkey
    FOREIGN KEY (agent_id) REFERENCES ibex_core.agents(id) ON DELETE CASCADE NOT VALID;
