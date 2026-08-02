-- Wave 2b: tenant-scoped ownership FKs for optional token subjects.
-- Prerequisite: agents already have UNIQUE (id, org_id) from 000009.
-- users need UNIQUE (id, org_id) before (user_id, org_id) can reference them.
--
-- Same-ID / wrong-org binds are nulled before VALIDATE. Existence-only orphans
-- cannot exist while 000008 single-column FKs are still in place (dropped below).
-- UNIQUE (id, org_id) matches 000009 agents pattern (not CONCURRENTLY): Phase-1
-- users is small; splitting index/constraint across migrations is unnecessary.

ALTER TABLE ibex_core.users
    ADD CONSTRAINT users_id_org_unique UNIQUE (id, org_id);

-- Null subjects whose parent row exists in a different org.
UPDATE ibex_core.tokens t
SET agent_id = NULL
FROM ibex_core.agents a
WHERE t.agent_id = a.id
  AND t.org_id <> a.org_id;

UPDATE ibex_core.tokens t
SET user_id = NULL
FROM ibex_core.users u
WHERE t.user_id = u.id
  AND t.org_id <> u.org_id;

ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_agent_id_fk;
ALTER TABLE ibex_core.tokens DROP CONSTRAINT IF EXISTS tokens_user_id_fk;

ALTER TABLE ibex_core.tokens
    ADD CONSTRAINT tokens_agent_org_fk
    FOREIGN KEY (agent_id, org_id)
    REFERENCES ibex_core.agents (id, org_id)
    ON DELETE CASCADE
    NOT VALID;

ALTER TABLE ibex_core.tokens
    ADD CONSTRAINT tokens_user_org_fk
    FOREIGN KEY (user_id, org_id)
    REFERENCES ibex_core.users (id, org_id)
    ON DELETE CASCADE
    NOT VALID;

ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_agent_org_fk;
ALTER TABLE ibex_core.tokens VALIDATE CONSTRAINT tokens_user_org_fk;
