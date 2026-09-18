-- Reverse 000037_privacy_governance.

REVOKE UPDATE (data, archived_to) ON ibex_core.session_events FROM ibex_app;
REVOKE UPDATE (data, archived_to) ON ibex_core.session_events FROM ibex_service;

DROP TRIGGER IF EXISTS deletion_store_receipts_updated_at ON ibex_core.deletion_store_receipts;
DROP TABLE IF EXISTS ibex_core.deletion_store_receipts;

DROP TRIGGER IF EXISTS org_capture_policies_updated_at ON ibex_core.org_capture_policies;
DROP TABLE IF EXISTS ibex_core.org_capture_policies;

DROP TABLE IF EXISTS ibex_core.legal_holds;

DROP TRIGGER IF EXISTS privacy_audit_ledger_no_update_delete ON ibex_core.privacy_audit_ledger;
DROP FUNCTION IF EXISTS ibex_core.privacy_audit_append(
    UUID, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT[], TEXT, TEXT, TEXT, TEXT, TEXT, JSONB
);
DROP FUNCTION IF EXISTS ibex_core.privacy_audit_list_orgs();
DROP FUNCTION IF EXISTS ibex_core.privacy_audit_ledger_forbid_mutate();
DROP TABLE IF EXISTS ibex_core.privacy_audit_ledger;
DROP FUNCTION IF EXISTS ibex_core.rls_privacy_visible(UUID);

-- Reconcile hold_blocked rows before restoring the narrower status check.
UPDATE ibex_core.org_deletion_jobs
SET status = 'failed',
    error = COALESCE(error, 'hold_blocked_rollback')
WHERE status = 'hold_blocked';

ALTER TABLE ibex_core.org_deletion_jobs
    DROP COLUMN IF EXISTS archived_uri_snapshot;

ALTER TABLE ibex_core.org_deletion_jobs
    DROP CONSTRAINT IF EXISTS org_deletion_jobs_status_check;

ALTER TABLE ibex_core.org_deletion_jobs
    ADD CONSTRAINT org_deletion_jobs_status_check
    CHECK (status IN ('pending', 'running', 'succeeded', 'failed'));
