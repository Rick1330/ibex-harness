-- Stage 2 privilege separation: the erasure proof and the erasure settlement
-- belong to the erasure worker, not to ibex_app.
--
-- Why this exists: ibex_app is the tenant request-path identity. ibex_runtime
-- (services/memory, services/api) is a member of it, so a tenant request could
-- insert a `verified` receipt with `verified_absent_at = NOW()`, change a failed
-- receipt to verified, or settle its own outbox row to `complete` without
-- deleting anything. RLS fences the organization, not the verification
-- authority, so the tenant predicate does not prevent a forged proof.
--
-- The fix is a separate capability role, in the same NOINHERIT, SET-ROLE-only
-- model as ibex_app and ibex_purge (000064):
--
--   ibex_erasure  NOLOGIN, member of nothing; SET-enabled only for ibex_worker.
--
-- It holds exactly the writes the consumer needs:
--   * erasure_store_receipts: SELECT, INSERT, UPDATE — the proof
--   * memory_lifecycle_outbox: SELECT plus column UPDATE on the settle columns
--   * memory_artifact_refs: SELECT — the worklist
--
-- ibex_app keeps only what the forget response needs to read its own state
-- (SELECT on both tables) plus its INSERT on memory_artifact_refs, which is the
-- capture archiver's provenance write and is not a proof.
--
-- Forward-only in production (ADR-0098). The down file restores the 000073/
-- 000074 grants and drops the role.

SET LOCAL lock_timeout = '5s';

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_erasure') THEN
        CREATE ROLE ibex_erasure NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
    ELSE
        ALTER ROLE ibex_erasure NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
    END IF;
END
$$;

-- The only intended path into the erasure identity is the worker login. Every
-- other capability role is explicitly denied, so a later GRANT cannot widen the
-- tenant request path silently.
GRANT ibex_erasure TO ibex_worker;
REVOKE ibex_erasure FROM ibex_app, ibex_runtime, ibex_bootstrap, ibex_service,
    ibex_purge, ibex_evidence_relay, ibex_auth;
-- Explicit denials, in the 000064 style: do not rely on absence. The erasure
-- identity must never reach the service, purge, or tenant identities.
REVOKE ibex_service, ibex_purge, ibex_app FROM ibex_erasure;

GRANT USAGE ON SCHEMA ibex_core TO ibex_erasure;

-- Policies execute as the querying user.
GRANT EXECUTE ON FUNCTION ibex_core.rls_org_visible(uuid) TO ibex_erasure;

-- The consumer reads the worklist, writes the proof, and settles the row.
GRANT SELECT ON ibex_core.memory_artifact_refs TO ibex_erasure;
GRANT SELECT, INSERT, UPDATE ON ibex_core.erasure_store_receipts TO ibex_erasure;
GRANT SELECT ON ibex_core.memory_lifecycle_outbox TO ibex_erasure;
GRANT UPDATE (attempts, locked_until, erasure_state, available_at, delivered_at)
    ON ibex_core.memory_lifecycle_outbox TO ibex_erasure;

-- Tighten the tenant identity: reads and the archiver's ref INSERT stay, the
-- proof writes and the settlement columns do not.
REVOKE INSERT, UPDATE ON ibex_core.erasure_store_receipts FROM ibex_app;
REVOKE UPDATE (attempts, locked_until, erasure_state, available_at, delivered_at)
    ON ibex_core.memory_lifecycle_outbox FROM ibex_app;

COMMENT ON ROLE ibex_erasure IS
    'NOLOGIN capability role for the memory-lifecycle erasure worker: writes erasure receipts and settles outbox rows; never held by the tenant request path.';
