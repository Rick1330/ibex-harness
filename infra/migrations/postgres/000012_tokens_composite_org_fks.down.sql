ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_user_org_fk;
ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_agent_org_fk;

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

ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_id_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_id_fk;

ALTER TABLE ibex_core.users DROP CONSTRAINT IF EXISTS users_id_org_unique;
