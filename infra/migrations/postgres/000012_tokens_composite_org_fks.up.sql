-- Wave 2b: tenant-scoped ownership FKs for optional token subjects.
-- Prerequisite: agents already have UNIQUE (id, org_id) from 000009.
-- users need UNIQUE (id, org_id) before (user_id, org_id) can reference them.
--
-- Cross-org orphans (IDs exist but wrong org) are nulled before VALIDATE so
-- environments that predate app-layer Wave 2a can migrate cleanly.

ALTER TABLE ibex_core.users
    ADD CONSTRAINT users_id_org_unique UNIQUE (id, org_id);

-- Clear same-ID / wrong-org binds (existence-only orphans are already handled by 000008).
UPDATE ibex_core.tokens t
SET agent_id = NULL
WHERE agent_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ibex_core.agents a
      WHERE a.id = t.agent_id
        AND a.org_id = t.org_id
  );

UPDATE ibex_core.tokens t
SET user_id = NULL
WHERE user_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM ibex_core.users u
      WHERE u.id = t.user_id
        AND u.org_id = t.org_id
  );

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
