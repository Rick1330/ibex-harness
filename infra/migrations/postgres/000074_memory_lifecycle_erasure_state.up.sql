-- Stage 2 memory-lifecycle erasure state, and the fourth store a memory forget
-- must prove.
--
-- Why this exists: the forget path writes a `memory_lifecycle_outbox` row (000045)
-- in the same transaction that tombstones the memory, but nothing consumed those
-- rows. A forget could therefore tombstone PostgreSQL and report success while
-- the memory's object-store archive, its ClickHouse evidence and the
-- `session_events` row that carried it still existed, with no record that the
-- erasure was attempted, let alone finished. 000072 records where those copies
-- live; 000073 records the per-store proof; this migration adds the state that
-- makes the consumer resumable and lets the forget response tell the truth.
--
-- `erasure_state` is the job state of one outbox row, not of one store:
--   pending  - no consumer has finished with this row yet (also the value every
--              pre-existing row gets, and every non-erasure event keeps: only
--              forgotten/purged/expired rows describe something to erase).
--   partial  - at least one store is unproven and a retry can still help.
--   complete - every store receipt is verified or not_applicable.
--   failed   - the erasure deadline passed with a store unproven; terminal, so a
--              permanently unreachable store cannot retry forever.
--
-- `erasure_deadline` bounds the whole erasure for one row. It is set when a
-- consumer first claims the row and is never extended, so a row that keeps
-- failing has one honest stop condition instead of an unbounded retry history.
--
-- Forward-only (ADR-0098): the down file drops both columns and refuses while any
-- row records erasure progress.

ALTER TABLE ibex_core.memory_lifecycle_outbox
    ADD COLUMN erasure_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (erasure_state IN ('pending','partial','complete','failed')),
    ADD COLUMN erasure_deadline TIMESTAMPTZ;

COMMENT ON COLUMN ibex_core.memory_lifecycle_outbox.erasure_state IS
    'Job state of the erasure this row describes: pending, partial, complete, or terminal failed.';
COMMENT ON COLUMN ibex_core.memory_lifecycle_outbox.erasure_deadline IS
    'Absolute deadline for the whole erasure of this row; set at first claim, never extended.';

-- No new claim index: `idx_memory_lifecycle_outbox_pending` (000045) is already
-- partial on `delivered_at IS NULL`, and the consumer filters event type and
-- erasure state over that same small set. A second near-identical index would be
-- write cost for no read gain.

-- 000073 keyed a receipt to (memory, revision, store) using the org-deletion
-- vocabulary: postgres / clickhouse / objectstore. A memory forget also erases
-- the `session_events` row that carried the memory, and that erasure needs its
-- own receipt or "erased everywhere" leaves one store unproven. The domain grows
-- by exactly that value; widening a CHECK cannot invalidate an existing row, and
-- the down file restores the narrower domain.
ALTER TABLE ibex_core.erasure_store_receipts
    DROP CONSTRAINT erasure_store_receipts_store_check;
ALTER TABLE ibex_core.erasure_store_receipts
    ADD CONSTRAINT erasure_store_receipts_store_check
    CHECK (store IN ('postgres','clickhouse','objectstore','session_event'));

-- Two grants the consumer needs, and deliberately no more:
--
-- * UPDATE on the outbox, column-scoped: 000045 granted ibex_app SELECT, INSERT
--   only — the memory service wrote events and read nothing back. Leasing a row
--   (attempts, locked_until) and settling it (erasure_state, delivered_at,
--   available_at) is an UPDATE, and without it the consumer can claim nothing.
--   The grant names those five columns and stops there. `org_id`, `memory_id`,
--   `revision` and `event_type` are the identity and the meaning of the row, so
--   a tenant identity able to rewrite them could forge `erasure_state =
--   'complete'` on a live `created` row, or retarget an erasure onto another
--   memory or tenant. Column-scoped grants are the 000064 style for exactly this
--   reason: the verb is not the privilege, the columns are.
-- * A column SELECT on `session_events.id` for `ibex_purge`, and nothing for
--   `ibex_app`. The `session_events` row is the fourth copy of a memory, but the
--   request-path identity must not hold DELETE on an append-only audit trail: it
--   would let a tenant delete evidence with no forget, no receipt and no
--   legal-hold check. That stage runs through `ibex_purge`, which already holds
--   DELETE (000064) and is the only identity the org-deletion saga trusts with
--   it. DELETE names one row by `id`, and PostgreSQL requires SELECT on a column
--   read in the WHERE clause, so the purge role gets that one column.
GRANT UPDATE (attempts, locked_until, erasure_state, available_at, delivered_at)
    ON ibex_core.memory_lifecycle_outbox TO ibex_app;
GRANT SELECT (id) ON ibex_core.session_events TO ibex_purge;

-- Discovery is the one step that cannot run as a tenant. The outbox is
-- RLS-scoped to `app.current_org_id`, so a sweep with no tenant selected sees no
-- rows at all — and a scheduled consumer has no org to select. The evidence
-- relay solved the same problem the same way (000036): a SECURITY DEFINER
-- function owned by `ibex_service` (NOLOGIN, NOBYPASSRLS since 000063) claims
-- across tenants and returns identifiers only, never content. It reaches every
-- tenant because `rls_org_visible` returns true when `current_user =
-- 'ibex_service'` (000063) — a policy branch, not a role attribute — so the
-- cross-tenant reach is auditable in the policy rather than in a BYPASSRLS flag.
-- Every statement after the claim runs as `ibex_app` with the claimed row's org
-- GUC, so the erasure itself stays inside one tenant boundary.
--
-- The claim does not exclude rows that a newer delivered revision already
-- superseded: the consumer retires those and copies the newer row's state, so
-- they leave the pending set with a recorded decision instead of being skipped
-- forever by a predicate nothing ever satisfies.
--
-- The lease and the deadline are arguments rather than constants so the worker's
-- configured budgets drive them; the bounds below keep a caller that skipped that
-- configuration from writing an absurd lease.
CREATE OR REPLACE FUNCTION ibex_core.memory_lifecycle_claim_erasure(
    p_limit INTEGER,
    p_lease_seconds DOUBLE PRECISION,
    p_deadline_seconds DOUBLE PRECISION
)
RETURNS TABLE (
    id UUID,
    org_id UUID,
    memory_id UUID,
    revision BIGINT,
    attempts INTEGER,
    event_type TEXT,
    erasure_deadline TIMESTAMPTZ
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ibex_core, pg_temp
AS $$
BEGIN
    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 64 THEN
        RAISE EXCEPTION 'memory_lifecycle_claim_erasure: p_limit must be between 1 and 64';
    END IF;
    -- The bounds live here as well as in the worker's Settings: the function is
    -- EXECUTE-able by the worker login, and a caller that skipped configuration
    -- validation must not be able to park a row under a multi-year lease or a
    -- deadline that never arrives.
    IF p_lease_seconds IS NULL OR p_lease_seconds <= 0 OR p_lease_seconds > 3600 THEN
        RAISE EXCEPTION 'memory_lifecycle_claim_erasure: p_lease_seconds must be in (0, 3600]';
    END IF;
    IF p_deadline_seconds IS NULL OR p_deadline_seconds <= 0
       OR p_deadline_seconds > 604800 THEN
        RAISE EXCEPTION 'memory_lifecycle_claim_erasure: p_deadline_seconds must be in (0, 604800]';
    END IF;
    RETURN QUERY
    UPDATE ibex_core.memory_lifecycle_outbox o
       SET attempts = o.attempts + 1,
           locked_until = NOW() + make_interval(secs => p_lease_seconds),
           erasure_deadline = COALESCE(
               o.erasure_deadline,
               NOW() + make_interval(secs => p_deadline_seconds)
           )
     WHERE o.id IN (
         SELECT c.id
           FROM ibex_core.memory_lifecycle_outbox c
          WHERE c.delivered_at IS NULL
            AND c.available_at <= NOW()
            AND (c.locked_until IS NULL OR c.locked_until < NOW())
            AND c.erasure_state IN ('pending', 'partial')
            -- Only the events that end a memory. A created/content_updated/
            -- superseded row describes a memory that still exists, and erasing
            -- its copies would delete live data.
            AND c.event_type IN ('forgotten', 'purged', 'expired')
          ORDER BY c.available_at, c.occurred_at, c.id
          FOR UPDATE SKIP LOCKED
          LIMIT p_limit
     )
    RETURNING o.id, o.org_id, o.memory_id, o.revision, o.attempts,
              o.event_type, o.erasure_deadline;
END;
$$;

ALTER FUNCTION ibex_core.memory_lifecycle_claim_erasure(INTEGER, DOUBLE PRECISION, DOUBLE PRECISION)
    OWNER TO ibex_service;
REVOKE ALL ON FUNCTION ibex_core.memory_lifecycle_claim_erasure(
    INTEGER, DOUBLE PRECISION, DOUBLE PRECISION) FROM PUBLIC;
-- Granted to the worker login, not to ibex_app: a tenant identity must not be
-- able to lease another tenant's erasure work. The worker then acts on each row
-- under that row's own org GUC.
GRANT EXECUTE ON FUNCTION ibex_core.memory_lifecycle_claim_erasure(
    INTEGER, DOUBLE PRECISION, DOUBLE PRECISION) TO ibex_worker;
