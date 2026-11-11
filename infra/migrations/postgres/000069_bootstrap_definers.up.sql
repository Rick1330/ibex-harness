-- P0-06 follow-up: the bootstrap definers.
--
-- `services/auth/internal/bootstrap` created the first organization, owner,
-- agent, model policy and credentials while setting the retired
-- `app.is_service_account` GUC. 000063 replaced that flag with
-- `current_user = 'ibex_service'`, and `ibex_service` is NOBYPASSRLS, so a
-- bootstrap process that pins the least-privilege `ibex_bootstrap` login cannot
-- read or write those tables at all.
--
-- Each write becomes a narrow SECURITY DEFINER function owned by
-- `ibex_service`: inside the definer `current_user` is the owner, so the tenant
-- policy admits the row without a forgeable GUC and without BYPASSRLS. The
-- bodies are the statements the Go command already issued, moved behind a
-- definer so `ibex_bootstrap` needs EXECUTE only — no table privilege and no
-- membership.
--
-- One write has no definer of its own. The default model policy (the allow-all
-- fallback and its epoch) is inserted by bootstrap_upsert_organization, in the
-- same statement that creates the organization row, because the policy belongs
-- to the moment of creation. Authorization for it is structural, not state
-- based; section 1 states the change and the trade-off.
--
-- `ibex_bootstrap` holding EXECUTE is NOT the same as "cannot reach another
-- organization": every p_org_id below is a caller-chosen value, and inside the
-- definer `rls_org_visible` admits every organization's rows. Three bodies
-- therefore refuse the writes that would let a caller act on a tenant it does
-- not own. The inventory below is the acceptance criterion: every refusal names
-- its function, rule and SQLSTATE, and the integration suite asserts each row.
--
--   function                        rule                                                SQLSTATE
--   ------------------------------  --------------------------------------------------  --------
--   bootstrap_create_identity       organization already has a users row                42501
--   bootstrap_insert_pat            permissions is not the bootstrap PAT grant          23514
--   bootstrap_insert_pat            organization already owns a pat row                  42501
--   bootstrap_insert_pat            user is not an active owner of the organization      23514
--   bootstrap_insert_pat            agent is not an active agent of the organization    23514
--   bootstrap_upsert_service_token  permissions is not the memory-service grant         23514
--   bootstrap_upsert_service_token  organization has no active owner or active agent    23514
--
-- The model policy has no refusal row because it has no call to refuse: it is
-- written only on the `created` branch of bootstrap_upsert_organization, so an
-- organization that already exists cannot receive it whatever its policy state.
--
-- The advisory locks are the second control, not a refusal: every body that
-- performs a check-then-write takes the per-organization lock first
-- (bootstrap_create_identity, bootstrap_insert_pat,
-- bootstrap_upsert_service_token), and the service-token body takes the
-- per-prefix lock after it. Lock order is org then prefix, so two definers
-- cannot deadlock; the serialization test asserts both locks.
--
-- Guard-to-test map (tenancy_bootstrap_definers_integration_test.go):
--
--   identity re-run / existing organization   TestTenancyBootstrapCreateIdentityGuard
--   PAT mask / second PAT / foreign subjects  TestTenancyBootstrapPATGuard
--   service-token mask / missing subject      TestTenancyBootstrapServiceTokenGuard
--   policy on create / existing organization  TestTenancyBootstrapModelPolicyGuard
--   org-then-prefix lock order                TestTenancyBootstrapSerializesPerOrg
--
-- The six functions map 1:1 to the old Go helpers:
--
--   bootstrap_upsert_organization   insertOrganization + insertModelPolicy
--   bootstrap_lock_organization     lockOrganization
--   bootstrap_lookup_subjects       lookupOwner / lookupAgent
--   bootstrap_create_identity       insertIdentity
--   bootstrap_insert_pat            insertToken
--   bootstrap_upsert_service_token  ensurePrefixUnused / findServiceTokens /
--                                   updateServiceToken / revokeDuplicate* /
--                                   insertServiceToken
--
-- The remaining cross-org capability is deliberate and bounded:
-- bootstrap_upsert_organization can create a new organization, and
-- bootstrap_lookup_subjects returns another organization's owner/agent ids
-- (ids only, no credential). Those two create a tenant or read ids; neither
-- writes into a tenant that already exists.
--
-- The model policy used to be a third. bootstrap_write_model_policy accepted
-- any organization id and refused only when that organization already had a
-- policy row or an epoch row. That is a state check, not an authorization: an
-- existing organization with neither row was indistinguishable from a fresh
-- install, so the allow-all fallback could be installed into a tenant an
-- operator had deliberately left unconfigured, and nothing in the call could
-- tell the caller's own new installation from somebody else's empty
-- organization. The write now sits inside the `IF created` branch of
-- bootstrap_upsert_organization, in the statement that inserts the organization
-- row: the definer already knows whether it created the tenant, so the policy
-- is written exactly when the tenant is, and there is no separate call to
-- authorize.
--
-- The function was dropped rather than left un-granted. It is owned by
-- `ibex_service`, and a role that can SET ROLE ibex_service (the `ibex`
-- migration login, 000064:140) executes an owner's function whatever the ACL
-- says, so removing the GRANT would have hidden the capability rather than
-- removed it. Dropping the function removes both paths, and the inventory above
-- no longer has to describe a rule nothing calls.
--
-- The trade-off is deliberate: the allow-all fallback now commits with the
-- organization, so an operator cannot create an organization through bootstrap
-- without it. That is the intended bootstrap state — a new tenant with no
-- policy is unusable until someone grants one — and every later policy change
-- is an operator action on the console/API, not a bootstrap one.
--
-- Deploy order: apply this migration with the bootstrap binary from the same
-- commit. An older binary calls the dropped function after the organization
-- insert, receives 42883 (undefined_function) and rolls the whole bootstrap
-- back, so a stale binary fails loudly instead of leaving a half-built
-- installation; a re-run against an existing organization never reached that
-- call and is unaffected.
--
-- Installation-scoped authorization is NOT expressible here, and no control
-- below pretends otherwise. `ibex_bootstrap` is a one-shot command, not a
-- per-request service: a definer sees `session_user = 'ibex_bootstrap'` and
-- nothing else. Every installation that pins that login is indistinguishable
-- from every other one, and a session GUC cannot supply the missing identity
-- because the caller would set it itself — it is a claim, not evidence. There
-- is also no row to derive an owner from: the organization this command exists
-- to create has no users, agents or tokens yet, and ships no creator marker.
-- The residual is therefore: a stolen `ibex_bootstrap` credential can create
-- state for any organization. That is why the credential is never used by a
-- long-running service, why it starts inert with CONNECTION LIMIT 0 until
-- `migrate provision` activates it, and why every body below bounds what it can
-- write per organization instead of trusting who is calling. The per-org guards
-- are the control; they are what keeps a stolen credential from taking over an
-- installation that already exists.
--
-- Every function is REVOKEd from PUBLIC and granted to `ibex_bootstrap` only.
-- The caller-facing text for the paths Go already models stays in Go: those
-- functions return data or a named outcome. A guard raises instead, because Go
-- has no branch for "this organization is already bootstrapped" and a returned
-- outcome nothing reads would be silent.

-- CREATE FUNCTION / ALTER FUNCTION / GRANT take catalog locks, and this file is
-- one transaction. Fail fast rather than queue behind a long reader (same
-- discipline as 000063).
SET LOCAL lock_timeout = '5s';

-- ================================================================
-- 1. Organization, and the default model policy it is born with
-- ================================================================
-- insertOrganization + insertModelPolicy. The tier/status/embedding literals are
-- the values the Go bootstrap wrote; they stay here so the definer is the only
-- writer and a caller cannot smuggle a different profile into a tenant.
--
-- The default model policy (allow-all fallback at priority 1000) and its epoch 1
-- mirror infra/scripts/seed_dev.sql. They are written only when this statement
-- inserted the organization row, which is the entire authorization for the
-- write: `created` is a fact about this call, not a property of the target. An
-- organization that already exists keeps whatever policy state its operator
-- chose — including none — and a caller naming an existing slug gets
-- created = false and no policy row. There is no separate definer to authorize,
-- so a bootstrap credential cannot add the fallback to a tenant it did not
-- create, and the empty-tenant case cannot be mistaken for a first install.
--
-- Both policy inserts are ON CONFLICT DO NOTHING: `created` is the only gate,
-- but a value already present (a retried statement, a seeded row) must still
-- leave exactly one fallback row and one epoch rather than raise.
CREATE OR REPLACE FUNCTION ibex_core.bootstrap_upsert_organization(
    p_id   uuid,
    p_name text,
    p_slug text
) RETURNS TABLE (
    created    boolean,
    org_id     uuid,
    deleted_at timestamptz
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
-- The OUT parameter `org_id` shares its name with the policy tables' tenant
-- column, and a bare `org_id` in the INSERT lists below would be ambiguous
-- (42702). Every bare name in this body is a column; the function's inputs are
-- all p_-prefixed.
#variable_conflict use_column
DECLARE
    v_inserted bigint;
BEGIN
    INSERT INTO ibex_core.organizations
        (id, name, slug, tier, status,
         embedding_profile, embedding_dim, embedding_model_id)
    VALUES
        (p_id, p_name, p_slug, 'free', 'active', 'gpu', 1024, 'BAAI/bge-m3')
    ON CONFLICT (slug) DO NOTHING;
    GET DIAGNOSTICS v_inserted = ROW_COUNT;

    -- The policy belongs to the moment of creation, so it commits or fails with
    -- the organization. If either insert raises, this statement aborts and the
    -- organization above goes with it: there is no path that leaves a tenant
    -- without its fallback.
    IF v_inserted > 0 THEN
        INSERT INTO ibex_core.org_model_policies (org_id, model_pattern, allowed, priority)
        VALUES (p_id, '*', true, 1000)
        ON CONFLICT (org_id, model_pattern) DO NOTHING;

        INSERT INTO ibex_core.org_model_policy_meta (org_id, epoch)
        VALUES (p_id, 1)
        ON CONFLICT (org_id) DO NOTHING;
    END IF;

    -- The conflict path re-reads the winner by slug: Go needs the existing org
    -- id, and `deleted_at` so its error can tell the operator to hard-delete the
    -- soft-deleted row or pick another slug.
    RETURN QUERY
    SELECT v_inserted > 0, o.id, o.deleted_at
    FROM ibex_core.organizations o
    WHERE o.slug = p_slug;
END;
$$;

ALTER FUNCTION ibex_core.bootstrap_upsert_organization(uuid, text, text) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_upsert_organization(uuid, text, text) FROM PUBLIC;

-- ================================================================
-- 2. Organization row lock
-- ================================================================
-- lockOrganization. Serializes memory-token reconciliation for one org. Returns
-- whether a non-deleted row exists so Go can fail with its own message.
CREATE OR REPLACE FUNCTION ibex_core.bootstrap_lock_organization(p_org_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_id uuid;
BEGIN
    SELECT o.id INTO v_id
    FROM ibex_core.organizations o
    WHERE o.id = p_org_id
      AND o.deleted_at IS NULL
    FOR UPDATE;
    RETURN FOUND;
END;
$$;

ALTER FUNCTION ibex_core.bootstrap_lock_organization(uuid) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_lock_organization(uuid) FROM PUBLIC;

-- ================================================================
-- 3. Subjects
-- ================================================================
-- lookupOwner / lookupAgent, in one call. Both reads return at most one row and
-- either id may be NULL, so Go can name which subject is missing before it
-- writes a token that would otherwise be accepted for any agent.
CREATE OR REPLACE FUNCTION ibex_core.bootstrap_lookup_subjects(p_org_id uuid)
RETURNS TABLE (
    owner_id uuid,
    agent_id uuid
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
    SELECT
        (SELECT u.id
           FROM ibex_core.users u
          WHERE u.org_id = p_org_id
            AND u.role = 'owner'
            AND u.status = 'active'
            AND u.deleted_at IS NULL
          ORDER BY u.created_at
          LIMIT 1),
        (SELECT a.id
           FROM ibex_core.agents a
          WHERE a.org_id = p_org_id
            AND a.status = 'active'
            AND a.deleted_at IS NULL
          ORDER BY a.created_at
          LIMIT 1);
$$;

ALTER FUNCTION ibex_core.bootstrap_lookup_subjects(uuid) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_lookup_subjects(uuid) FROM PUBLIC;

-- ================================================================
-- 4. Identity
-- ================================================================
-- insertIdentity. The owner user and the default agent are created together;
-- the agent's created_by is the user created in the same call.
--
-- Guard: an organization that already has a users row is an existing install,
-- and this function exists only to create the first one. Without the guard a
-- bootstrap caller could name any organization and add an owner user to it,
-- then use bootstrap_insert_pat to mint that tenant a credential. `users` is
-- visible across organizations here because the policy admits
-- `current_user = 'ibex_service'`, so the EXISTS below sees every tenant.
--
-- The EXISTS and the two INSERTs are one check-then-write, and two concurrent
-- calls for the same organization would both see no row and both insert. The
-- per-organization advisory lock below serializes them; it is taken before the
-- check and released at COMMIT, and the second caller re-reads under READ
-- COMMITTED after the first commits. Lock order is org first, then prefix (see
-- bootstrap_upsert_service_token), so two definers cannot deadlock.
CREATE OR REPLACE FUNCTION ibex_core.bootstrap_create_identity(
    p_org_id      uuid,
    p_user_id     uuid,
    p_user_email  text,
    p_user_name   text,
    p_agent_id    uuid,
    p_agent_name  text,
    p_agent_slug  text
) RETURNS TABLE (
    user_id  uuid,
    agent_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(hashtext(p_org_id::text));

    IF EXISTS (
        SELECT 1 FROM ibex_core.users u WHERE u.org_id = p_org_id
    ) THEN
        RAISE EXCEPTION
            'bootstrap_create_identity: organization % already has a users row; this is a re-run of an existing install, not a first install',
            p_org_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    INSERT INTO ibex_core.users (id, org_id, email, name, role, status)
    VALUES (p_user_id, p_org_id, p_user_email, p_user_name, 'owner', 'active');

    INSERT INTO ibex_core.agents (id, org_id, created_by, name, slug, status)
    VALUES (p_agent_id, p_org_id, p_user_id, p_agent_name, p_agent_slug, 'active');

    RETURN QUERY SELECT p_user_id, p_agent_id;
END;
$$;

ALTER FUNCTION ibex_core.bootstrap_create_identity(uuid, uuid, text, text, uuid, text, text) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_create_identity(uuid, uuid, text, text, uuid, text, text) FROM PUBLIC;

-- ================================================================
-- 5. Bootstrap PAT
-- ================================================================
-- insertToken. The id, prefix and Argon2id hash are generated by Go; only the
-- hash reaches the database.
--
-- Guards, because every argument is caller-chosen and the function runs as
-- `ibex_service` across organizations:
--
--   mask        the only PAT this function may write is the bootstrap PAT, so
--               the mask is fixed here instead of inserted verbatim (NULL and
--               every other value, supersets included, are refused). Without
--               this a caller could mint a full-admin credential for itself and
--               file it against another organization's subject ids.
--   one PAT     bootstrap issues exactly one PAT per organization and never
--               rotates it, so an existing `type = 'pat'` row means this is a
--               re-run, not a first install. The per-organization advisory lock
--               serializes the check against a concurrent call, which would
--               otherwise let two bootstraps both see no row and both insert.
--   subjects    the user must be that organization's active owner and the agent
--               its active agent, so a PAT can never be bound across tenants.
--
-- c_bootstrap_permissions is permissions.Admin | permissions.SecretUse |
-- permissions.OperatorMetadataRead — the value of bootstrapPermissions() in
-- services/auth/internal/bootstrap/bootstrap.go. The two are one constant in
-- two languages: change both, and the integration suite compares them.
CREATE OR REPLACE FUNCTION ibex_core.bootstrap_insert_pat(
    p_token_id    uuid,
    p_org_id      uuid,
    p_user_id     uuid,
    p_agent_id    uuid,
    p_hash        text,
    p_prefix      text,
    p_name        text,
    p_permissions bigint
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    c_bootstrap_permissions constant bigint := 35455006347011;
    -- The three refusals below are the same class of failure, so the SQLSTATE is
    -- named once. A guard that raised a different code would be a different
    -- contract for the caller.
    c_check_violation constant text := 'check_violation';
BEGIN
    IF p_permissions IS DISTINCT FROM c_bootstrap_permissions THEN
        RAISE EXCEPTION
            'bootstrap_insert_pat: permissions % is not the bootstrap PAT grant %; this function writes that mask only',
            p_permissions, c_bootstrap_permissions
            USING ERRCODE = c_check_violation;
    END IF;

    PERFORM pg_advisory_xact_lock(hashtext(p_org_id::text));

    IF EXISTS (
        SELECT 1 FROM ibex_core.tokens t
        WHERE t.org_id = p_org_id
          AND t.type = 'pat'
    ) THEN
        RAISE EXCEPTION
            'bootstrap_insert_pat: organization % already owns a pat row; bootstrap issues exactly one PAT and never rotates it',
            p_org_id
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM ibex_core.users u
        WHERE u.id = p_user_id
          AND u.org_id = p_org_id
          AND u.role = 'owner'
          AND u.status = 'active'
          AND u.deleted_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'bootstrap_insert_pat: user % is not an active owner of organization %',
            p_user_id, p_org_id
            USING ERRCODE = c_check_violation;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM ibex_core.agents a
        WHERE a.id = p_agent_id
          AND a.org_id = p_org_id
          AND a.status = 'active'
          AND a.deleted_at IS NULL
    ) THEN
        RAISE EXCEPTION
            'bootstrap_insert_pat: agent % is not an active agent of organization %',
            p_agent_id, p_org_id
            USING ERRCODE = c_check_violation;
    END IF;

    INSERT INTO ibex_core.tokens
        (id, org_id, user_id, agent_id, type, hash, prefix, name,
         permissions, is_revoked, expires_at)
    VALUES
        (p_token_id, p_org_id, p_user_id, p_agent_id, 'pat', p_hash, p_prefix, p_name,
         p_permissions, false, NULL);
    RETURN p_token_id;
END;
$$;

ALTER FUNCTION ibex_core.bootstrap_insert_pat(uuid, uuid, uuid, uuid, text, text, text, bigint) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_insert_pat(uuid, uuid, uuid, uuid, text, text, text, bigint) FROM PUBLIC;

-- ================================================================
-- 6. Memory service token
-- ================================================================
-- The reconcile path: ensurePrefixUnused + findServiceTokens + update/insert +
-- revokeDuplicateServiceTokens, in one call. Returns a named outcome so the
-- operator-facing text stays in Go:
--
--   inserted          no managed row existed; one was created
--   updated           the managed row was re-bound to the new hash/prefix
--   prefix_conflict   another organization already owns the prefix
--   revoked_refused   the managed row is revoked and must not be resurrected
--
-- The subjects are read and validated before either write: an organization
-- with no active owner or no active agent cannot hold a service token, and the
-- old INSERT wrote NULL into both columns because only Go checked. The mask is
-- fixed here too: the update branch below is a rotation, and without the guard a
-- caller could rotate the service credential up to a full-admin grant.
CREATE OR REPLACE FUNCTION ibex_core.bootstrap_upsert_service_token(
    p_org_id      uuid,
    p_hash        text,
    p_prefix      text,
    p_permissions bigint
) RETURNS TABLE (
    outcome  text,
    token_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    -- permissions.MemoryRead | permissions.MemoryWrite, the value Go's
    -- writeServiceToken passes (services/auth/internal/bootstrap/bootstrap.go).
    c_service_token_permissions constant bigint := 3;
    -- The managed row is identified by these two values in the find, the insert
    -- and the duplicate sweep. Named once so no branch can look for a row the
    -- other branch would not have written, and the guard SQLSTATE once so both
    -- refusals stay the same contract.
    c_token_type      constant text := 'service_token';
    c_token_name      constant text := 'memory-service';
    c_check_violation constant text := 'check_violation';
    v_token_id uuid;
    v_revoked  boolean;
    v_user_id  uuid;
    v_agent_id uuid;
BEGIN
    IF p_permissions IS DISTINCT FROM c_service_token_permissions THEN
        RAISE EXCEPTION
            'bootstrap_upsert_service_token: permissions % is not the memory-service grant %; this function writes that mask only',
            p_permissions, c_service_token_permissions
            USING ERRCODE = c_check_violation;
    END IF;

    -- Lock order: org first, then prefix, in every body that takes either
    -- (bootstrap_create_identity, bootstrap_insert_pat, and here). Two definers
    -- that acquire the pair in one order cannot deadlock. Both keys come from
    -- hashtext, so a collision between an org and a prefix only over-serializes;
    -- it cannot invert the order.
    PERFORM pg_advisory_xact_lock(hashtext(p_org_id::text));

    -- ensurePrefixUnused. The validator resolves a bearer by prefix alone and
    -- returns exactly one row, so a prefix shared by two organizations makes
    -- the older tenant's bearer stop validating: cross-tenant denial of
    -- authentication, not a cosmetic collision.
    --
    -- Two layers. This transaction-scoped advisory lock serializes concurrent
    -- calls for the same prefix (hashtext collisions only over-serialize) so
    -- the EXISTS below cannot miss a row a competing call is about to commit.
    -- The structural guarantee is the unique index idx_tokens_prefix_unique
    -- (000071), which covers every other writer too.
    PERFORM pg_advisory_xact_lock(hashtext(p_prefix));

    -- The caller's own organization is excluded: on the rotation path the
    -- managed row already carries this prefix, and that is not a conflict.
    IF EXISTS (
        SELECT 1 FROM ibex_core.tokens t
        WHERE t.prefix = p_prefix
          AND t.org_id <> p_org_id
    ) THEN
        RETURN QUERY SELECT 'prefix_conflict'::text, NULL::uuid;
        RETURN;
    END IF;

    -- Guard: both subjects are required, and both are re-read here rather than
    -- trusted from the caller. bootstrap_lookup_subjects returns NULL for a
    -- missing subject, which is exactly the value the INSERT used to write.
    SELECT s.owner_id, s.agent_id
      INTO v_user_id, v_agent_id
      FROM ibex_core.bootstrap_lookup_subjects(p_org_id) AS s;

    IF v_user_id IS NULL OR v_agent_id IS NULL THEN
        RAISE EXCEPTION
            'bootstrap_upsert_service_token: organization % has no active owner user (owner_id %) or no active agent (agent_id %); both subjects are required',
            p_org_id, v_user_id, v_agent_id
            USING ERRCODE = c_check_violation;
    END IF;

    -- findServiceTokens: the managed row is the one already carrying this hash
    -- when a previous write landed, otherwise the organization's oldest
    -- `type = 'service_token'` / `name = 'memory-service'` row. Preferring the
    -- hash match makes a re-run idempotent and guarantees the UPDATE below can
    -- never collide with tokens_hash_key: when no row holds p_hash, setting it
    -- on the chosen row is unique by definition. The id tiebreaker keeps the
    -- winner deterministic when two rows share a timestamp.
    SELECT t.id, t.is_revoked
      INTO v_token_id, v_revoked
      FROM ibex_core.tokens t
     WHERE t.org_id = p_org_id
       AND t.type = c_token_type
       AND t.name = c_token_name
     ORDER BY (t.hash = p_hash) DESC, t.created_at, t.id
     LIMIT 1;

    IF NOT FOUND THEN
        -- insertServiceToken.
        INSERT INTO ibex_core.tokens
            (id, org_id, user_id, agent_id, type, hash, prefix, name,
             permissions, is_revoked, expires_at)
        VALUES
            (gen_random_uuid(), p_org_id, v_user_id, v_agent_id, c_token_type,
             p_hash, p_prefix, c_token_name, p_permissions, false, NULL)
        RETURNING id INTO v_token_id;

        RETURN QUERY SELECT 'inserted'::text, v_token_id;
        RETURN;
    END IF;

    IF v_revoked THEN
        -- updateServiceToken: never resurrect a credential the operator
        -- revoked. Failing the one-shot makes the state visible instead of
        -- silently re-enabling the old grant.
        RETURN QUERY SELECT 'revoked_refused'::text, v_token_id;
        RETURN;
    END IF;

    -- updateServiceToken: rotation writes the new hash/prefix and re-binds the
    -- row to the organization's current owner and agent, already read and
    -- validated above. `updated_at = NOW()` is explicit even though the trigger
    -- sets it, so the UPDATE column list and the granted columns are one set.
    UPDATE ibex_core.tokens
       SET hash = p_hash,
           prefix = p_prefix,
           permissions = p_permissions,
           user_id = v_user_id,
           agent_id = v_agent_id,
           expires_at = NULL,
           updated_at = NOW()
     WHERE id = v_token_id
       AND org_id = p_org_id;

    -- revokeDuplicateServiceTokens: disable every later managed row so the
    -- organization ends the call with exactly one active memory-service token.
    UPDATE ibex_core.tokens
       SET is_revoked = true,
           revoked_at = NOW(),
           revoke_reason = 'duplicate memory-service row',
           updated_at = NOW()
     WHERE org_id = p_org_id
       AND type = c_token_type
       AND name = c_token_name
       AND id <> v_token_id
       AND NOT is_revoked;

    RETURN QUERY SELECT 'updated'::text, v_token_id;
END;
$$;

ALTER FUNCTION ibex_core.bootstrap_upsert_service_token(uuid, text, text, bigint) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.bootstrap_upsert_service_token(uuid, text, text, bigint) FROM PUBLIC;

-- ================================================================
-- Caller: the bootstrap login, and only it. `ibex_bootstrap` already holds
-- USAGE on ibex_core from 000064; it gets no table privilege here.
-- ================================================================
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_upsert_organization(uuid, text, text) TO ibex_bootstrap;
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_lock_organization(uuid) TO ibex_bootstrap;
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_lookup_subjects(uuid) TO ibex_bootstrap;
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_create_identity(uuid, uuid, text, text, uuid, text, text) TO ibex_bootstrap;
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_insert_pat(uuid, uuid, uuid, uuid, text, text, text, bigint) TO ibex_bootstrap;
GRANT EXECUTE ON FUNCTION ibex_core.bootstrap_upsert_service_token(uuid, text, text, bigint) TO ibex_bootstrap;

-- ================================================================
-- Column privileges the definer bodies need as `ibex_service`
-- ================================================================
-- RLS still applies to the owner (it is NOBYPASSRLS); the 000063 policies admit
-- `current_user = 'ibex_service'`. Column-scoped: no memory content, credential
-- or secret column is granted, and every column below is named by a body above.

-- `SELECT (slug)` is the ON CONFLICT arbiter in bootstrap_upsert_organization
-- and the `WHERE o.slug = p_slug` re-read. `SELECT (id, status, deleted_at)` is
-- already granted by 000065:234.
GRANT SELECT (slug) ON ibex_core.organizations TO ibex_service;
-- The insertOrganization column list, in full.
GRANT INSERT (id, name, slug, tier, status, embedding_profile, embedding_dim, embedding_model_id)
    ON ibex_core.organizations TO ibex_service;
-- DELIBERATE, do not remove: measured on PostgreSQL 16, `SELECT ... FOR UPDATE`
-- (bootstrap_lock_organization) requires UPDATE privilege on at least one
-- column of the locked table and never writes that column. `id` is that column.
-- Its SELECT grant already exists in 000065.
GRANT UPDATE (id) ON ibex_core.organizations TO ibex_service;

-- lookupOwner predicate and ORDER BY (bootstrap_lookup_subjects), and the
-- owner-binding guard in bootstrap_insert_pat.
GRANT SELECT (id, org_id, role, status, deleted_at, created_at)
    ON ibex_core.users TO ibex_service;
-- insertIdentity column list.
GRANT INSERT (id, org_id, email, name, role, status)
    ON ibex_core.users TO ibex_service;

-- lookupAgent predicate and ORDER BY (bootstrap_lookup_subjects), and the
-- agent-binding guard in bootstrap_insert_pat.
GRANT SELECT (id, org_id, status, deleted_at, created_at)
    ON ibex_core.agents TO ibex_service;
-- insertIdentity column list.
GRANT INSERT (id, org_id, created_by, name, slug, status)
    ON ibex_core.agents TO ibex_service;

-- The find and prefix-ownership predicates in bootstrap_upsert_service_token.
-- `SELECT (id, org_id, user_id, agent_id, permissions, expires_at, hash,
-- prefix, is_revoked, created_at)` is already granted by 000065:232.
GRANT SELECT (type, name) ON ibex_core.tokens TO ibex_service;
-- insertToken and insertServiceToken column lists.
GRANT INSERT (id, org_id, user_id, agent_id, type, hash, prefix, name,
              permissions, is_revoked, expires_at)
    ON ibex_core.tokens TO ibex_service;
-- updateServiceToken (hash, prefix, permissions, user_id, agent_id,
-- expires_at, updated_at) and revokeDuplicateServiceTokens (is_revoked,
-- revoked_at, revoke_reason, updated_at).
GRANT UPDATE (hash, prefix, permissions, user_id, agent_id, expires_at,
              updated_at, is_revoked, revoked_at, revoke_reason)
    ON ibex_core.tokens TO ibex_service;

-- The policy inserts in bootstrap_upsert_organization: insertModelPolicy's column
-- list, now part of the organization body.
GRANT INSERT (org_id, model_pattern, allowed, priority)
    ON ibex_core.org_model_policies TO ibex_service;
GRANT INSERT (org_id, epoch)
    ON ibex_core.org_model_policy_meta TO ibex_service;
-- The ON CONFLICT arbiter is a row read, and the read is subject to RLS.
-- Measured on PostgreSQL 16: an explicit `ON CONFLICT (org_id, model_pattern)`
-- requires SELECT on both arbiter columns even for DO NOTHING, and
-- `ON CONFLICT (org_id)` requires SELECT on org_id. Without these,
-- bootstrap_upsert_organization fails with "permission denied for table" on a
-- fresh install, which is the only path that writes a policy.
GRANT SELECT (org_id, model_pattern) ON ibex_core.org_model_policies TO ibex_service;
GRANT SELECT (org_id) ON ibex_core.org_model_policy_meta TO ibex_service;
