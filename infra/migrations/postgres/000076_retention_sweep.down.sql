-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Drops the three retention functions (their ACL entries go with them) and
-- revokes the column privileges 000076 added to `ibex_service`. The grants on
-- `idempotency_ledger` pre-date this migration and are not touched.

DROP FUNCTION IF EXISTS ibex_core.retention_delete_finalized_idempotency(timestamptz);
DROP FUNCTION IF EXISTS ibex_core.retention_delete_failed_tasks(timestamptz);
DROP FUNCTION IF EXISTS ibex_core.retention_scrub_failed_tasks(timestamptz);

REVOKE SELECT (id, failed_at, exception_message, traceback),
       UPDATE (args, kwargs, exception_message, traceback),
       DELETE
    ON ibex_core.failed_tasks FROM ibex_service;
