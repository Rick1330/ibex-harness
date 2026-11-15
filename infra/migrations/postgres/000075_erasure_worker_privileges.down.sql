-- Roll back the erasure-worker capability role.
--
-- This restores the 000073/000074 grant set (ibex_app may write receipts and
-- settle outbox rows) and drops ibex_erasure. Forward-only in production
-- (ADR-0098); this file exists for dev rollback and for the migration tests.
--
-- Roles are cluster-global, so DROP ROLE can fail with 2BP01 when another
-- database in the same cluster still uses the role. That is not a reason to
-- leave this database half-rolled-back: the grants and membership are revoked
-- unconditionally, and the drop is best effort. The up file normalises a
-- pre-existing role through its own idempotent guard.

SET LOCAL lock_timeout = '5s';

GRANT INSERT, UPDATE ON ibex_core.erasure_store_receipts TO ibex_app;
GRANT UPDATE (attempts, locked_until, erasure_state, available_at, delivered_at)
    ON ibex_core.memory_lifecycle_outbox TO ibex_app;

REVOKE UPDATE (attempts, locked_until, erasure_state, available_at, delivered_at)
    ON ibex_core.memory_lifecycle_outbox FROM ibex_erasure;
REVOKE SELECT ON ibex_core.memory_lifecycle_outbox FROM ibex_erasure;
REVOKE SELECT, INSERT, UPDATE ON ibex_core.erasure_store_receipts FROM ibex_erasure;
REVOKE SELECT ON ibex_core.memory_artifact_refs FROM ibex_erasure;
REVOKE EXECUTE ON FUNCTION ibex_core.rls_org_visible(uuid) FROM ibex_erasure;
REVOKE USAGE ON SCHEMA ibex_core FROM ibex_erasure;
REVOKE ibex_erasure FROM ibex_worker;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_erasure') THEN
        BEGIN
            DROP ROLE ibex_erasure;
        EXCEPTION WHEN dependent_objects_still_exist THEN
            -- Another database in the cluster still grants the role; the
            -- grants in this database are already revoked above.
            NULL;
        END;
    END IF;
END
$$;
