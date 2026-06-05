-- Add the deferred FK constraints noted in DATABASE_SCHEMA.md.
-- Executed as NOT VALID to avoid a full table scan on the existing
-- tokens rows (which currently have NULL values in these columns).
-- VALIDATE CONSTRAINT is run separately below to allow concurrent reads.

ALTER TABLE ibex_core.tokens
    ADD CONSTRAINT tokens_user_id_fk
    FOREIGN KEY (user_id)
    REFERENCES ibex_core.users(id)
    ON DELETE CASCADE
    NOT VALID;

ALTER TABLE ibex_core.tokens
    ADD CONSTRAINT tokens_agent_id_fk
    FOREIGN KEY (agent_id)
    REFERENCES ibex_core.agents(id)
    ON DELETE CASCADE
    NOT VALID;

ALTER TABLE ibex_core.tokens
    ADD CONSTRAINT tokens_revoked_by_fk
    FOREIGN KEY (revoked_by)
    REFERENCES ibex_core.users(id)
    ON DELETE SET NULL
    NOT VALID;

-- Validate now (existing rows should have NULL values, so this is instant).
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_id_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_id_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_revoked_by_fk;

