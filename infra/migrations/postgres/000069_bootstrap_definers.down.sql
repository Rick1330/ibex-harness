-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Reverses 000069: drops the six bootstrap definers (their EXECUTE ACLs go
-- with them) and revokes exactly the column privileges they added to
-- `ibex_service`. The default model policy has no definer of its own — it was
-- written by bootstrap_upsert_organization — so dropping that function drops
-- the policy write with it.
--
-- It deliberately does NOT `DROP OWNED BY ibex_service`: that would strip the
-- reader grants 000065 gives the service identity, which this migration did not
-- add and must not remove.

DROP FUNCTION IF EXISTS ibex_core.bootstrap_upsert_service_token(uuid, text, text, bigint);
DROP FUNCTION IF EXISTS ibex_core.bootstrap_insert_pat(uuid, uuid, uuid, uuid, text, text, text, bigint);
DROP FUNCTION IF EXISTS ibex_core.bootstrap_create_identity(uuid, uuid, text, text, uuid, text, text);
DROP FUNCTION IF EXISTS ibex_core.bootstrap_lookup_subjects(uuid);
DROP FUNCTION IF EXISTS ibex_core.bootstrap_lock_organization(uuid);
DROP FUNCTION IF EXISTS ibex_core.bootstrap_upsert_organization(uuid, text, text);

REVOKE SELECT (slug) ON ibex_core.organizations FROM ibex_service;
REVOKE INSERT (id, name, slug, tier, status, embedding_profile, embedding_dim, embedding_model_id)
    ON ibex_core.organizations FROM ibex_service;
REVOKE UPDATE (id) ON ibex_core.organizations FROM ibex_service;

REVOKE SELECT (id, org_id, role, status, deleted_at, created_at)
    ON ibex_core.users FROM ibex_service;
REVOKE INSERT (id, org_id, email, name, role, status)
    ON ibex_core.users FROM ibex_service;

REVOKE SELECT (id, org_id, status, deleted_at, created_at)
    ON ibex_core.agents FROM ibex_service;
REVOKE INSERT (id, org_id, created_by, name, slug, status)
    ON ibex_core.agents FROM ibex_service;

REVOKE SELECT (type, name) ON ibex_core.tokens FROM ibex_service;
REVOKE INSERT (id, org_id, user_id, agent_id, type, hash, prefix, name,
               permissions, is_revoked, expires_at)
    ON ibex_core.tokens FROM ibex_service;
REVOKE UPDATE (hash, prefix, permissions, user_id, agent_id, expires_at,
               updated_at, is_revoked, revoked_at, revoke_reason)
    ON ibex_core.tokens FROM ibex_service;

REVOKE INSERT (org_id, model_pattern, allowed, priority)
    ON ibex_core.org_model_policies FROM ibex_service;
REVOKE INSERT (org_id, epoch)
    ON ibex_core.org_model_policy_meta FROM ibex_service;
REVOKE SELECT (org_id, model_pattern)
    ON ibex_core.org_model_policies FROM ibex_service;
REVOKE SELECT (org_id)
    ON ibex_core.org_model_policy_meta FROM ibex_service;
