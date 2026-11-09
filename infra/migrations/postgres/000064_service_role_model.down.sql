-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Reverses 000064: restores 000062's two DELETE grants, drops the legal-holds
-- trigger, removes the memberships this migration added, drops every privilege
-- granted to the capability roles, and drops the roles themselves.

-- ================================================================
-- Restore 000062 / 000037
-- ================================================================
GRANT DELETE ON ibex_core.session_events TO ibex_service;
GRANT DELETE ON ibex_core.directive_versions TO ibex_service;
GRANT DELETE ON ibex_core.legal_holds TO ibex_service;

-- Restore the two ibex_app EXECUTE grants revoked by `up`.
GRANT EXECUTE ON FUNCTION ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
) TO ibex_app;
GRANT EXECUTE ON FUNCTION ibex_billing.clear_enforcement_budget_period_id() TO ibex_app;

-- ================================================================
-- Legal-holds guard
-- ================================================================
DROP TRIGGER IF EXISTS legal_holds_reject_active_delete ON ibex_core.legal_holds;
DROP FUNCTION IF EXISTS ibex_core.legal_holds_reject_active_delete();

-- ================================================================
-- Memberships (DROP OWNED does not remove role memberships)
-- ================================================================
REVOKE ibex_app FROM ibex_runtime, ibex_worker;
REVOKE ibex_purge FROM ibex_worker;
REVOKE ibex_service FROM ibex;

-- ================================================================
-- Privileges granted to the capability roles
-- ================================================================
-- 000064 added UPDATE (session_id) and SELECT (session_id) on memories for the
-- session-delete trigger. DROP OWNED removes them; the explicit revoke keeps
-- the up/down pair auditable.
REVOKE SELECT (org_id, session_id, id, lifecycle_revision), UPDATE (session_id), DELETE
    ON ibex_core.memories FROM ibex_purge;

DROP OWNED BY ibex_purge, ibex_runtime, ibex_worker, ibex_bootstrap;

DROP ROLE IF EXISTS ibex_bootstrap, ibex_worker, ibex_runtime, ibex_purge;
