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
            'ibex_auth pre-exists with a credential outside the capability role model (needs a direct, SET-enabled ibex_app membership); repair with GRANT ibex_app TO ibex_auth WITH ADMIN FALSE, INHERIT FALSE, SET TRUE, or drop the foreign role, then re-run the migration';
    END IF;
END
$$;

-- ================================================================
-- Membership and explicit denials
-- ================================================================
-- Normalize the membership options on every run. A plain `GRANT` leaves an
-- existing pg_auth_members row untouched (measured on PostgreSQL 16: re-granting
-- a row granted WITH ADMIN TRUE keeps admin_option true), so a login that
-- arrived with options this model never emits would keep them. The model's shape
-- is ADMIN FALSE, INHERIT FALSE, SET TRUE: NOINHERIT means the tenant identity is
-- usable only through SET ROLE, and no other option is ever set. The provenance
-- guard above tests `set_option`, so a row that carries ADMIN or INHERIT is not
-- the shape this model produces yet still passes it; this statement is what
-- returns such a row to the model. The regression test starts from a
-- `WITH ADMIN TRUE, INHERIT TRUE` row and asserts the options below.
--
-- Normalizing the options is not enough on its own. A row granted WITH ADMIN
-- TRUE may have let ibex_auth grant ibex_app onward, and those dependent rows
-- carry grantor = ibex_auth. They are separate pg_auth_members rows, so the
-- GRANT below clears admin_option without touching them, and ibex_auth keeps
-- the delegated tenant identity it handed to another role (measured on
-- PostgreSQL 16: the dependent row survives the option change). REVOKE ADMIN
-- OPTION ... CASCADE removes exactly those rows, so it has to run BEFORE the
-- GRANT: once admin_option is false there is no admin grant left to cascade
-- from, and the dependent rows survive. The statement is a no-op when ibex_auth
-- never held the admin option.
--
-- If the revoke is rejected (for example because this transaction is not the
-- grantor and lacks ADMIN OPTION on ibex_app), stop with the repair instead of
-- leaving the dependent rows in place and reporting success.
DO $$
BEGIN
    BEGIN
        REVOKE ADMIN OPTION FOR ibex_app FROM ibex_auth CASCADE;
    EXCEPTION WHEN OTHERS THEN
        RAISE EXCEPTION
            'ibex_auth holds dependent ibex_app grants that could not be withdrawn automatically (%); revoke the roles ibex_auth granted ibex_app to, then re-run this migration',
            SQLERRM
            USING ERRCODE = 'insufficient_privilege';
    END;
END
$$;

GRANT ibex_app TO ibex_auth WITH ADMIN FALSE, INHERIT FALSE, SET TRUE;

-- Do not rely on absence: a future GRANT must not be able to turn the auth
-- login into a service, purge, bootstrap, worker or relay identity silently.
REVOKE ibex_service FROM ibex_auth;
REVOKE ibex_purge FROM ibex_auth;
REVOKE ibex_bootstrap FROM ibex_auth;
REVOKE ibex_worker FROM ibex_auth;
REVOKE ibex_evidence_relay FROM ibex_auth;

-- Needed to resolve the schema-qualified reader as the login. Tenant queries
-- run inside SET ROLE ibex_app and use ibex_app's grants.
GRANT USAGE ON SCHEMA ibex_core TO ibex_auth;

-- ================================================================
-- Token lookup moves from ibex_runtime to ibex_auth
-- ================================================================
-- The order (grant, then revoke) is not an atomicity device. This file is one
-- transaction, so both ACL changes become visible together at COMMIT and
-- swapping the statements would change nothing.
--
-- What the order describes is the intended two-release cutover: grant the
-- reader to ibex_auth in the release that introduces the auth login, and revoke
-- it from ibex_runtime only once no ibex_runtime process still reads it. Both
-- land here, so that cutover is collapsed into one commit: the moment this
-- transaction commits, an ibex_runtime process from the previous release loses
-- EXECUTE and fails with `42501 permission denied for function
-- auth_find_token_by_prefix` — a hard error on every bearer it tries to resolve,
-- not a clean deny. Drain the ibex_runtime fleet before this migration runs, or
-- move the REVOKE into its own later migration.
GRANT EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) TO ibex_auth;
REVOKE EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) FROM ibex_runtime;
