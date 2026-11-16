-- P1-21 / P2-12 / P2-15: bounded retention for stores that outlive their use.
--
-- Three windows, each a policy decision recorded here rather than in a caller:
--
--   ibex_core.failed_tasks        content scrubbed at 7 days, row deleted at 30
--   ibex_core.idempotency_ledger  finalized rows deleted after 24 hours
--   ibex.usage_facts              whole months older than 13 dropped
--
-- The Postgres sweep runs as one SECURITY DEFINER function per window, owned by
-- `ibex_service` (the pattern from 000065). It has to: `failed_tasks` carries no
-- RLS and grants only INSERT to `ibex_app`, and `idempotency_ledger` is FORCE
-- RLS, so `ibex_worker` can reach neither table directly and must not be given
-- the grants to do it. Inside the definer `current_user` is `ibex_service`, which
-- `rls_org_visible` admits, so the cross-tenant reach comes from the function
-- owner and never from a forgeable GUC.
--
-- Every function validates its cutoff the same way: required, and never in the
-- future. A future cutoff would delete or scrub rows the window has not reached.
--
-- ClickHouse has no function layer and no RLS; its window is enforced by
-- `services/worker/app/retention.py` dropping whole `usage_facts` partitions,
-- which is a recorded exception to "every ClickHouse statement names org_id"
-- (a partition covers every tenant, and dropping it is the retention policy).

SET LOCAL lock_timeout = '5s';

-- ================================================================
-- retention_scrub_failed_tasks
-- Overwrites the payload-bearing columns of every dead-letter row older than
-- the scrub window. Idempotent by construction: an already-scrubbed row is
-- excluded, so a second run matches nothing and reports zero.
--
-- `failed_at` is the only time column, and it is set once at insert, so the
-- scrub cannot race a later write that would repopulate the columns.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.retention_scrub_failed_tasks(p_before timestamptz)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF p_before IS NULL THEN
        RAISE EXCEPTION 'retention_scrub_failed_tasks: before is required'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_before > NOW() THEN
        RAISE EXCEPTION 'retention_scrub_failed_tasks: before must be <= NOW()'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    WITH scrubbed AS (
        UPDATE ibex_core.failed_tasks
        SET args = '[]'::jsonb,
            kwargs = '{}'::jsonb,
            exception_message = '[scrubbed]',
            traceback = '[scrubbed]'
        WHERE failed_at < p_before
          AND (exception_message <> '[scrubbed]' OR traceback <> '[scrubbed]')
        RETURNING 1
    )
    SELECT count(*) INTO v_rows FROM scrubbed;

    RETURN v_rows;
END;
$$;

ALTER FUNCTION ibex_core.retention_scrub_failed_tasks(timestamptz) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.retention_scrub_failed_tasks(timestamptz) FROM PUBLIC;

-- ================================================================
-- retention_delete_failed_tasks
-- Drops dead-letter rows past the retention window. `org_id` is nullable and
-- the table has no RLS: one sweep covers every tenant, which is the point of a
-- dead-letter store.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.retention_delete_failed_tasks(p_before timestamptz)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF p_before IS NULL THEN
        RAISE EXCEPTION 'retention_delete_failed_tasks: before is required'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_before > NOW() THEN
        RAISE EXCEPTION 'retention_delete_failed_tasks: before must be <= NOW()'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    DELETE FROM ibex_core.failed_tasks WHERE failed_at < p_before;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RETURN v_rows;
END;
$$;

ALTER FUNCTION ibex_core.retention_delete_failed_tasks(timestamptz) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.retention_delete_failed_tasks(timestamptz) FROM PUBLIC;

-- ================================================================
-- retention_delete_finalized_idempotency
-- Removes replay records that can no longer serve a retry. The `finalized`
-- predicate is the safety rule, not a convenience filter: a `claimed` or
-- `reconciling` row is a live in-flight claim, and deleting it would let the
-- caller's retry execute twice.
--
-- There is no finalized_at column; `updated_at` is the finalize instant, set by
-- Finalize and never advanced again for a finalized row.
-- ================================================================
CREATE OR REPLACE FUNCTION ibex_core.retention_delete_finalized_idempotency(p_before timestamptz)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
DECLARE
    v_rows bigint;
BEGIN
    IF p_before IS NULL THEN
        RAISE EXCEPTION 'retention_delete_finalized_idempotency: before is required'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_before > NOW() THEN
        RAISE EXCEPTION 'retention_delete_finalized_idempotency: before must be <= NOW()'
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    DELETE FROM ibex_core.idempotency_ledger
    WHERE state = 'finalized'
      AND updated_at < p_before;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RETURN v_rows;
END;
$$;

ALTER FUNCTION ibex_core.retention_delete_finalized_idempotency(timestamptz) OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.retention_delete_finalized_idempotency(timestamptz) FROM PUBLIC;

-- ================================================================
-- Privileges the definer bodies need as `ibex_service`. Column-scoped on the
-- one table that holds content: the scrub overwrites args/kwargs/message/
-- traceback and reads the two columns it compares. `failed_tasks` carries no
-- tenant policy, so `ibex_service` reads every tenant's row by design.
-- `idempotency_ledger` already grants SELECT/DELETE to `ibex_service` (000043,
-- 000044); nothing is added for it here.
-- ================================================================
GRANT SELECT (id, failed_at, exception_message, traceback),
      UPDATE (args, kwargs, exception_message, traceback),
      DELETE
    ON ibex_core.failed_tasks TO ibex_service;

-- ================================================================
-- Callers: the worker login only. The tenant role gets nothing, and
-- `ibex_worker` is NOINHERIT, so EXECUTE is the whole capability.
-- ================================================================
GRANT EXECUTE ON FUNCTION ibex_core.retention_scrub_failed_tasks(timestamptz) TO ibex_worker;
GRANT EXECUTE ON FUNCTION ibex_core.retention_delete_failed_tasks(timestamptz) TO ibex_worker;
GRANT EXECUTE ON FUNCTION ibex_core.retention_delete_finalized_idempotency(timestamptz) TO ibex_worker;
