-- Dev/rollback only. Production migrations are forward-only (ADR-0098).
--
-- Drops the five readers (their ACL entries go with them) and revokes the
-- column privileges they added to `ibex_service`. Budget-reservation and
-- budget-period privileges pre-date this migration and are not touched.

DROP FUNCTION IF EXISTS ibex_billing.active_periods();
DROP FUNCTION IF EXISTS ibex_core.budget_reservations_expire_stale(interval, int);
DROP FUNCTION IF EXISTS ibex_core.sessions_abandon_idle(timestamptz, int);
DROP FUNCTION IF EXISTS ibex_core.rate_limit_overrides_snapshot();
DROP FUNCTION IF EXISTS ibex_core.auth_find_token_by_prefix(text);

REVOKE SELECT (id, org_id, user_id, agent_id, permissions, expires_at, hash, prefix, is_revoked)
    ON ibex_core.tokens FROM ibex_service;
REVOKE SELECT (id, status, deleted_at)
    ON ibex_core.organizations FROM ibex_service;
REVOKE SELECT (org_id, agent_id, requests_per_minute)
    ON ibex_core.rate_limit_overrides FROM ibex_service;
REVOKE SELECT (id, org_id, agent_id, external_id, status, deleted_at, updated_at),
       UPDATE (status, completed_at)
    ON ibex_core.sessions FROM ibex_service;
