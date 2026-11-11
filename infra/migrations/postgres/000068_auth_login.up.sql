-- P0-06 follow-up: a dedicated login for the auth service.
--
-- `ibex_runtime` is a member of `ibex_app`, so every process that can resolve a
-- bearer also holds full tenant read/write. Token resolution needs exactly one
-- capability: the SECURITY DEFINER reader `ibex_core.auth_find_token_by_prefix`,
-- which is already owned by `ibex_service` and already grants the caller no
-- table privilege. It moves to a login of its own:
--
--   ibex_auth   member of ibex_app, EXECUTE on the token reader only
--
-- The role is created inert (no password, CONNECTION LIMIT 0); `migrate
-- provision` is the only writer of its credential. NOINHERIT means the ibex_app
-- membership is usable only through SET ROLE, exactly like the other capability
-- logins, so an auth process cannot carry the tenant identity into an ordinary
-- query by accident.

-- ALTER ROLE / GRANT on a function take locks on the pg_authid and pg_proc
-- rows, and this file is one transaction. Fail fast instead of queueing behind a
-- long catalog reader (same discipline as 000063).
SET LOCAL lock_timeout = '5s';

-- ================================================================
-- Role
-- ================================================================
DO $$
DECLARE
    auth_created  boolean;
    auth_modelled boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_auth') THEN -- NOSONAR: ALTER ROLE attributes cannot be parameterised; the role restates the capability attribute set deliberately
        CREATE ROLE ibex_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT CONNECTION LIMIT 0;
        auth_created := true;
    ELSE
        -- Deliberately no CONNECTION LIMIT here: a role that `migrate provision`
        -- already activated must survive a re-run of this file with its -1
        -- limit, exactly like 000064's ELSE branches.
        ALTER ROLE ibex_auth LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
        auth_created := false;
    END IF;

    -- A direct row with SET only, captured before this file grants anything.
    -- Every capability role is NOINHERIT, so a membership is usable only
    -- through SET ROLE; `m.set_option` is the flag that decides whether it can
    -- be assumed at all. `pg_has_role(..., 'MEMBER')` is not used because it
    -- counts transitive membership, and a bare EXISTS is not enough because a
    -- `SET FALSE` row is a deliberately narrowed membership rather than
    -- evidence this model produced the role.
    auth_modelled :=
        EXISTS (
            SELECT 1 FROM pg_auth_members m
            JOIN pg_roles granted ON granted.oid = m.roleid
            JOIN pg_roles member  ON member.oid  = m.member
            WHERE granted.rolname = 'ibex_app' AND member.rolname = 'ibex_auth'
              AND m.set_option
        );

    PERFORM set_config('ibex.created_auth', auth_created::text, true);
    PERFORM set_config('ibex.auth_modelled', auth_modelled::text, true);
END
$$;

-- ================================================================
-- Provenance guard
-- ================================================================
-- Roles and memberships are cluster-global, so a second database in a
-- provisioned cluster re-runs this file against a login that `migrate
-- provision` already secured. `provision` cannot commit unless every role it
-- manages is reachable from the login it provisions, but it never issues a
-- GRANT and its reachability check is option-blind. The shape this file
-- creates is a direct, SET-enabled `ibex_app` row, and that row (captured
-- above, before any GRANT in this file ran) is the provenance signal.
--
-- A credential alone is not drift: that is the provisioned case. A role with a
-- credential and no direct, SET-enabled `ibex_app` row is foreign, and the
-- unconditional GRANT below would silently hand it the tenant identity, so stop
-- and name the repair instead.
DO $$
BEGIN
    IF current_setting('ibex.created_auth', true) IS DISTINCT FROM 'true'
       AND EXISTS (SELECT 1 FROM pg_authid WHERE rolname = 'ibex_auth' AND rolpassword IS NOT NULL)
       AND current_setting('ibex.auth_modelled', true) IS DISTINCT FROM 'true' THEN
        RAISE EXCEPTION
            'ibex_auth pre-exists with a credential outside the capability role model (needs a direct, SET-enabled ibex_app membership); repair with GRANT ibex_app TO ibex_auth, or drop the foreign role, then re-run the migration';
    END IF;
END
$$;

-- ================================================================
-- Membership and explicit denials
-- ================================================================
GRANT ibex_app TO ibex_auth;

-- Do not rely on absence: a future GRANT must not be able to turn the auth
-- login into a service, purge or bootstrap identity silently.
REVOKE ibex_service FROM ibex_auth;
REVOKE ibex_purge FROM ibex_auth;
REVOKE ibex_bootstrap FROM ibex_auth;

-- Needed to resolve the schema-qualified reader as the login. Tenant queries
-- run inside SET ROLE ibex_app and use ibex_app's grants.
GRANT USAGE ON SCHEMA ibex_core TO ibex_auth;

-- ================================================================
-- Token lookup moves from ibex_runtime to ibex_auth
-- ================================================================
-- Order matters. A rolling deploy keeps an old ibex_runtime process and a new
-- ibex_auth process alive at the same time; if the REVOKE ran first there would
-- be a window in which neither login could resolve a bearer, and every request
-- in that window fails closed. Grant first, revoke second, one transaction.
GRANT EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) TO ibex_auth;
REVOKE EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) FROM ibex_runtime;
