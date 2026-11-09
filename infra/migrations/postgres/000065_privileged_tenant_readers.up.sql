-- P0-06 foundation: privileged cross-tenant readers.
--
-- Five operations legitimately need cross-tenant reach:
--
--   auth token lookup by prefix          services/auth/internal/repository/tokens.go
--   rate-limit override full poll        packages/ratelimit/config_store.go
--   idle-session abandon sweep           packages/session/abandon_idle.go
--   stale budget-reservation sweep       services/worker/app/budget_ledger.py
--   active budget-period rollup          services/worker/app/tasks/billing_reconcile.py
--
-- Each becomes a SECURITY DEFINER function owned by `ibex_service`. Inside the
-- definer `current_user` is `ibex_service`, so the tenant policy permits the
-- read without a forgeable GUC and without BYPASSRLS. The callers get EXECUTE
-- only to the function they use; the tenant role gets nothing.

-- ================================================================
-- auth_find_token_by_prefix
-- Exactly the eight columns scanned by tokens.go:35-58.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.auth_find_token_by_prefix(p_prefix text)
RETURNS TABLE (
    token_id      text,
    org_id        text,
    org_status    text,
    user_id       text,
    agent_id      text,
    permissions   bigint,
    expires_at    timestamptz,
    token_hash    text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF p_prefix IS NULL OR char_length(p_prefix) < 1 OR char_length(p_prefix) > 256 THEN
        RAISE EXCEPTION 'auth_find_token_by_prefix: prefix must be 1..256 characters'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    RETURN QUERY
    SELECT t.id::text,
           t.org_id::text,
           o.status,
           t.user_id::text,
           t.agent_id::text,
           t.permissions,
           t.expires_at,
           t.hash
    FROM ibex_core.tokens t
    INNER JOIN ibex_core.organizations o ON o.id = t.org_id
    WHERE t.prefix = p_prefix
      AND t.is_revoked = false
      AND (t.expires_at IS NULL OR t.expires_at > NOW())
      AND o.deleted_at IS NULL
    LIMIT 1;
END;
$$;

ALTER FUNCTION ibex_core.auth_find_token_by_prefix(text) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.auth_find_token_by_prefix(text) FROM PUBLIC;

-- ================================================================
-- rate_limit_overrides_snapshot
-- Exactly the columns read at config_store.go:77-78 (org_id uuid,
-- agent_id text or NULL, requests_per_minute int64).
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.rate_limit_overrides_snapshot()
RETURNS TABLE (
    org_id              uuid,
    agent_id            text,
    requests_per_minute bigint
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
    SELECT r.org_id,
           r.agent_id::text,
           r.requests_per_minute::bigint
    FROM ibex_core.rate_limit_overrides r;
$$;

ALTER FUNCTION ibex_core.rate_limit_overrides_snapshot() OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.rate_limit_overrides_snapshot() FROM PUBLIC;

-- ================================================================
-- sessions_abandon_idle
-- The cross-tenant sweep at abandon_idle.go:25-40, with the caller's 5000-row
-- clamp enforced inside the function too.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.sessions_abandon_idle(
    p_idle_before timestamptz,
    p_max_rows    int
)
RETURNS TABLE (
    id          uuid,
    org_id      uuid,
    agent_id    uuid,
    external_id text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_limit int;
BEGIN
    IF p_idle_before IS NULL THEN
        RAISE EXCEPTION 'sessions_abandon_idle: idle_before is required'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_idle_before > NOW() THEN
        RAISE EXCEPTION 'sessions_abandon_idle: idle_before must be <= NOW()'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_max_rows IS NULL OR p_max_rows < 1 THEN
        RAISE EXCEPTION 'sessions_abandon_idle: max_rows must be positive'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    v_limit := LEAST(p_max_rows, 5000);

    RETURN QUERY
    WITH victims AS (
        SELECT s.id
        FROM ibex_core.sessions s
        WHERE s.status = 'active'
          AND s.deleted_at IS NULL
          AND s.updated_at < p_idle_before
        ORDER BY s.updated_at ASC
        LIMIT v_limit
        FOR UPDATE SKIP LOCKED
    )
    UPDATE ibex_core.sessions AS s
    SET status = 'abandoned', completed_at = NOW()
    FROM victims AS v
    WHERE s.id = v.id AND s.status = 'active'
    RETURNING s.id, s.org_id, s.agent_id, s.external_id;
END;
$$;

ALTER FUNCTION ibex_core.sessions_abandon_idle(timestamptz, int) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.sessions_abandon_idle(timestamptz, int) FROM PUBLIC;

-- ================================================================
-- budget_reservations_expire_stale
-- The sweep at budget_ledger.py:280-298 / 616-628. Returns the expired ids so
-- the caller can count exactly what changed.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.budget_reservations_expire_stale(
    p_grace    interval,
    p_max_rows int
)
RETURNS SETOF uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_limit int;
BEGIN
    IF p_grace IS NULL OR p_grace < interval '0' THEN
        RAISE EXCEPTION 'budget_reservations_expire_stale: grace must be non-negative'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_max_rows IS NULL OR p_max_rows < 1 THEN
        RAISE EXCEPTION 'budget_reservations_expire_stale: max_rows must be positive'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    v_limit := LEAST(p_max_rows, 5000);

    RETURN QUERY
    WITH stale AS (
        SELECT r.id, r.version
        FROM ibex_core.budget_reservations r
        WHERE r.state = 'claimed'
          AND r.lease_expires_at <= NOW() - p_grace
        ORDER BY r.lease_expires_at
        LIMIT v_limit
    )
    UPDATE ibex_core.budget_reservations r
    SET state = 'expired',
        lease_expires_at = NULL,
        version = r.version + 1,
        updated_at = NOW()
    FROM stale
    WHERE r.id = stale.id
      AND r.state = 'claimed'
      AND r.version = stale.version
      AND r.lease_expires_at <= NOW() - p_grace
    RETURNING r.id;
END;
$$;

ALTER FUNCTION ibex_core.budget_reservations_expire_stale(interval, int) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.budget_reservations_expire_stale(interval, int) FROM PUBLIC;

-- ================================================================
-- ibex_billing.active_periods
-- The read at billing_reconcile.py:150-170; ids are returned as text exactly
-- as the query casts them.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_billing.active_periods()
RETURNS TABLE (
    period_id    text,
    org_id       text,
    period_start timestamptz,
    period_end   timestamptz
)
LANGUAGE sql
SECURITY DEFINER
SET search_path = ibex_billing, pg_temp
AS $$
    SELECT p.id::text,
           p.org_id::text,
           p.period_start,
           p.period_end
    FROM ibex_billing.budget_periods p
    WHERE p.period_start <= NOW()
      AND p.period_end > NOW();
$$;

ALTER FUNCTION ibex_billing.active_periods() OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_billing.active_periods() FROM PUBLIC;

-- ================================================================
-- Privileges the definer bodies need as `ibex_service` (RLS still applies to
-- the owner because it is NOBYPASSRLS; the policy admits `current_user`).
-- Column-scoped: no content, credential, or secret column is granted.
-- ================================================================
GRANT SELECT (id, org_id, user_id, agent_id, permissions, expires_at, hash, prefix, is_revoked)
    ON ibex_core.tokens TO ibex_service;
GRANT SELECT (id, status, deleted_at)
    ON ibex_core.organizations TO ibex_service;
GRANT SELECT (org_id, agent_id, requests_per_minute)
    ON ibex_core.rate_limit_overrides TO ibex_service;
GRANT SELECT (id, org_id, agent_id, external_id, status, deleted_at, updated_at),
      UPDATE (status, completed_at)
    ON ibex_core.sessions TO ibex_service;

-- ================================================================
-- Callers: the runtime login for the request-path readers, the worker login
-- for the sweeps. The tenant role is not granted any of them.
-- ================================================================
GRANT EXECUTE ON FUNCTION ibex_core.auth_find_token_by_prefix(text) TO ibex_runtime;
GRANT EXECUTE ON FUNCTION ibex_core.rate_limit_overrides_snapshot() TO ibex_runtime;
GRANT EXECUTE ON FUNCTION ibex_core.sessions_abandon_idle(timestamptz, int) TO ibex_runtime;
GRANT EXECUTE ON FUNCTION ibex_core.budget_reservations_expire_stale(interval, int) TO ibex_worker;
GRANT EXECUTE ON FUNCTION ibex_billing.active_periods() TO ibex_worker;
