-- P0-06 foundation: the service role model.
--
-- Three capability logins, each inert until `migrate provision` sets a
-- password (they are created with none):
--
--   ibex_runtime    member of ibex_app       (tenant request paths)
--   ibex_worker     member of ibex_app and
--                   ibex_purge               (tenant work + org purge)
--   ibex_bootstrap  no memberships            (reserved for a narrow PR-3
--                                              bootstrap definer; inert)
--
-- `ibex_purge` is the NOLOGIN role that runs the organization-deletion saga.
-- It is org-GUC-scoped (every saga statement filters a known `org_id`) and it
-- is deliberately NOT a member of `ibex_service`.
--
-- All four roles are NOINHERIT: memberships are only usable via SET ROLE, so a
-- login cannot accidentally carry the purge or service identity into an
-- ordinary tenant query.

-- CREATE TRIGGER takes SHARE ROW EXCLUSIVE on legal_holds (measured via
-- pg_locks): concurrent writes wait, reads proceed. Fail fast if the table is
-- busy rather than queue behind a long writer.
SET LOCAL lock_timeout = '5s';

-- ================================================================
-- Roles
-- ================================================================
DO $$
DECLARE
    purge_created  boolean;
    worker_created boolean;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_purge') THEN -- NOSONAR: ALTER ROLE attributes cannot be parameterised; each role restates the same attribute set deliberately
        CREATE ROLE ibex_purge NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
        purge_created := true;
    ELSE
        ALTER ROLE ibex_purge NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
        purge_created := false;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_runtime') THEN
        CREATE ROLE ibex_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT CONNECTION LIMIT 0;
    ELSE
        ALTER ROLE ibex_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_worker') THEN
        CREATE ROLE ibex_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT CONNECTION LIMIT 0;
        worker_created := true;
    ELSE
        ALTER ROLE ibex_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
        worker_created := false;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ibex_bootstrap') THEN
        CREATE ROLE ibex_bootstrap LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT CONNECTION LIMIT 0;
    ELSE
        ALTER ROLE ibex_bootstrap LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
    END IF;

    PERFORM set_config('ibex.created_purge', purge_created::text, true);
    PERFORM set_config('ibex.created_worker', worker_created::text, true);
END
$$;

-- ================================================================
-- Memberships (the only intended paths into each capability)
-- ================================================================
GRANT ibex_app TO ibex_runtime, ibex_worker;

-- Grant ibex_purge to ibex_worker only when this migration created the pair,
-- or when the pre-existing pair is already part of the capability role model.
-- Roles and memberships are cluster-global, so a second database in a
-- provisioned cluster re-runs this file against a login that `migrate
-- provision` already secured. `provision` cannot commit unless ibex_worker is
-- a member of ibex_purge, so that membership is the provenance signal: a
-- credential alone is not drift. Without the membership the role is foreign and
-- granting ibex_purge would silently widen it, so stop and tell the operator to
-- re-provision.
--
-- The ibex_purge guard stays on bare credential presence: provisionTargets has
-- no ibex_purge entry, so `provision` can never set a verifier on it, and any
-- credential there is genuine out-of-band drift.
DO $$
BEGIN
    IF current_setting('ibex.created_purge', true) IS DISTINCT FROM 'true'
       AND EXISTS (SELECT 1 FROM pg_authid WHERE rolname = 'ibex_purge' AND rolpassword IS NOT NULL) THEN
        RAISE EXCEPTION
            'ibex_purge pre-exists with a credential; re-provision the capability logins';
    END IF;
    IF current_setting('ibex.created_worker', true) IS DISTINCT FROM 'true'
       AND EXISTS (SELECT 1 FROM pg_authid WHERE rolname = 'ibex_worker' AND rolpassword IS NOT NULL) THEN
        -- Nested deliberately: `pg_has_role` raises for a missing role, and
        -- AND-clause evaluation order is not guaranteed.
        IF NOT pg_has_role('ibex_worker', 'ibex_purge', 'MEMBER') THEN
            RAISE EXCEPTION
                'ibex_worker pre-exists with a credential outside the capability role model; re-provision the capability logins';
        END IF;
    END IF;
END
$$;

GRANT ibex_purge TO ibex_worker;
GRANT ibex_service TO ibex;

-- Explicit denials. Do not rely on absence: a future GRANT must not be able to
-- turn a tenant login into a service or purge identity silently.
REVOKE ibex_service FROM ibex_app, ibex_runtime, ibex_worker, ibex_bootstrap, ibex_purge, ibex_evidence_relay;
REVOKE ibex_purge FROM ibex_app, ibex_runtime, ibex_bootstrap, ibex_service, ibex_evidence_relay;
REVOKE ibex_app FROM ibex_bootstrap, ibex_purge, ibex_service, ibex_evidence_relay;

-- ================================================================
-- Schema usage (needed to resolve a schema-qualified function as the login;
-- tenant queries run inside SET ROLE ibex_app and use ibex_app's grants)
-- ================================================================
GRANT USAGE ON SCHEMA ibex_core TO ibex_runtime, ibex_worker, ibex_bootstrap, ibex_purge;
GRANT USAGE ON SCHEMA ibex_billing TO ibex_worker;

-- ================================================================
-- ibex_purge grants. Each block names the statement in
-- services/worker/app/tasks/org_deletion.py that it covers. Column-scoped
-- SELECT is what the RLS predicate evaluates; it deliberately does not expose
-- memory content, credentials, token hashes, TOTP secrets, or hold reasons.
-- ================================================================

-- _claim_job / _finish_job / _load_archived_uri_snapshot /
-- _save_archived_uri_snapshot. The saga only claims and finishes an existing
-- job; the API creates it as ibex_app, so ibex_purge gets no INSERT.
GRANT SELECT (id, org_id, status, started_at, archived_uri_snapshot)
    ON ibex_core.org_deletion_jobs TO ibex_purge;
GRANT UPDATE (status, started_at, error, finished_at, archived_uri_snapshot)
    ON ibex_core.org_deletion_jobs TO ibex_purge;

-- upsert_receipt (INSERT ... ON CONFLICT DO UPDATE), _latest_receipt_status
-- (SELECT), _receipt_digests (SELECT). INSERT stays column-scoped to the
-- repository's explicit column list.
GRANT SELECT (job_id, store, status, verified_absent_at, error, updated_at, idempotency_key)
    ON ibex_core.deletion_store_receipts TO ibex_purge;
GRANT INSERT (job_id, store, scope, status, verified_absent_at, idempotency_key, error)
    ON ibex_core.deletion_store_receipts TO ibex_purge;
GRANT UPDATE (status, verified_absent_at, error, updated_at)
    ON ibex_core.deletion_store_receipts TO ibex_purge;

-- _has_active_legal_hold (SELECT org_id, cleared_at) and the cleared-only
-- DELETE in _PG_PRE_CASCADE. The BEFORE DELETE trigger below rejects an active
-- hold even if a future statement forgets `cleared_at IS NOT NULL`.
GRANT SELECT (org_id, cleared_at), DELETE ON ibex_core.legal_holds TO ibex_purge;

-- _collect_archived_uris (SELECT org_id, archived_to) and the pre-cascade
-- DELETE.
GRANT SELECT (org_id, archived_to), DELETE ON ibex_core.session_events TO ibex_purge;

-- `UPDATE sessions SET directive_version_id = NULL ...` and the cascade DELETE.
GRANT SELECT (org_id), UPDATE (directive_version_id), DELETE ON ibex_core.sessions TO ibex_purge;

-- The `purged` lifecycle event inserted from the memories DELETE's RETURNING.
GRANT INSERT ON ibex_core.memory_lifecycle_outbox TO ibex_purge;

-- Soft-cancel: SELECT id (policy) and deleted_at (COALESCE), UPDATE status and
-- deleted_at.
GRANT SELECT (id, deleted_at), UPDATE (status, deleted_at) ON ibex_core.organizations TO ibex_purge;

-- _PG_PRE_CASCADE evidence/policy/credential DELETEs. The policy helper reads
-- org_id; every statement filters the same org_id. No content column is
-- granted.
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_outbox TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_tool_audits TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_directive_snapshots TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_score_candidates TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_assembly_metrics TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_events TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_spans TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.evidence_runs TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.org_capture_policies TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.org_model_policies TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.org_model_policy_meta TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.provider_credentials TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.rate_limit_overrides TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.user_totp_secrets TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.operator_action_ledger TO ibex_purge;

-- _CASCADE_STATEMENTS tenant DELETEs. memories additionally RETURNINGs
-- org_id, id, lifecycle_revision into memory_lifecycle_outbox, so those three
-- columns are readable; `content` is not.
GRANT SELECT (org_id), DELETE ON ibex_core.memory_feedback TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.memory_conflict_escalations TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.memory_relationships TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.memory_labels TO ibex_purge;
-- memories additionally RETURNINGs org_id, id, lifecycle_revision into
-- memory_lifecycle_outbox. `UPDATE (session_id)` is required because deleting a
-- session fires `clear_memory_session_id`, which runs as ibex_purge and updates
-- memories.session_id for that session. The session_id SELECT is what the
-- trigger's WHERE clause reads.
GRANT SELECT (org_id, session_id, id, lifecycle_revision), UPDATE (session_id), DELETE
    ON ibex_core.memories TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.directive_versions TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.directives TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.tokens TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.agents TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.organization_invites TO ibex_purge;
GRANT SELECT (org_id), DELETE ON ibex_core.users TO ibex_purge;

-- _audit_append: append-only ledger is writable only through its SECURITY
-- DEFINER helper.
GRANT EXECUTE ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) TO ibex_purge;

-- Policies execute as the querying user.
GRANT EXECUTE ON FUNCTION ibex_core.rls_org_visible(uuid),
                        ibex_core.rls_evidence_visible(uuid),
                        ibex_core.rls_privacy_visible(uuid)
    TO ibex_purge;

-- ================================================================
-- Defense in depth: the purge identity cannot delete an active (uncleared)
-- hold even if a caller forgets the `cleared_at IS NOT NULL` predicate.
--
-- The guard is scoped to `ibex_purge` on purpose. The owner login and an
-- explicit maintenance path must stay able to clean up holds; a tenant-safety
-- trigger must not block operator recovery. `ibex_service` loses DELETE below,
-- so the only delete paths are the purge role and the owner.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.legal_holds_reject_active_delete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF current_user = 'ibex_purge' AND OLD.cleared_at IS NULL THEN
        RAISE EXCEPTION 'legal_holds: refusing to delete active hold org_id=%', OLD.org_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN OLD;
END;
$$;

CREATE TRIGGER legal_holds_reject_active_delete
    BEFORE DELETE ON ibex_core.legal_holds
    FOR EACH ROW EXECUTE FUNCTION ibex_core.legal_holds_reject_active_delete();

-- ================================================================
-- The two 000062 grants move to ibex_purge. ibex_service keeps its column
-- UPDATE on session_events from 000037.
-- ================================================================
REVOKE DELETE ON ibex_core.session_events FROM ibex_service;
REVOKE DELETE ON ibex_core.directive_versions FROM ibex_service;

-- 000037 granted DELETE on legal_holds to ibex_service. The saga now runs as
-- ibex_purge, so the broad service identity loses the verb: the only delete
-- paths are ibex_purge (cleared holds, guarded by the trigger) and the owner.
REVOKE DELETE ON ibex_core.legal_holds FROM ibex_service;

-- ================================================================
-- Two over-broad definer grants, verified against every caller in services/
-- and packages/ before removing.
-- ================================================================
-- The only privacy_audit_append caller is services/worker/app/tasks/
-- org_deletion.py (the purge path, which uses ibex_purge and keeps EXECUTE).
-- packages/privacyaudit only reads the ledger; services/api only reads it.
REVOKE EXECUTE ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) FROM ibex_app;

-- clear_enforcement_budget_period_id is a trigger function. Triggers fire
-- without an EXECUTE check on the invoking role, and no caller invokes it
-- directly.
REVOKE EXECUTE ON FUNCTION ibex_billing.clear_enforcement_budget_period_id() FROM ibex_app;
