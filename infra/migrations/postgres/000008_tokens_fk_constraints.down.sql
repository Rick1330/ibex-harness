ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_revoked_by_fk;
ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_agent_id_fk;
ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_user_id_fk;

