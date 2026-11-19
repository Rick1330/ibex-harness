"""Statements the erasure consumer runs.

Every statement names the org as well as the row. RLS already fences the row,
but AGENTS.md §4.1 requires the explicit predicate in the query too: one defence
that is switched off by a role attribute or a policy edit must not be the only
thing standing between one tenant's settle and another's row.

No statement is built from a value: identifiers are bound, and the table names
are literals. ``test_sql_is_literal_not_built_from_values`` reads this module.
"""

from __future__ import annotations

# SECURITY DEFINER claim: the outbox is RLS-scoped to app.current_org_id, and a
# scheduled consumer has no tenant to select, so discovery cannot run as a
# tenant. The function returns identifiers only; everything after it is
# tenant-scoped.
_CLAIM_SQL = """
SELECT id::text AS id, org_id::text AS org_id, memory_id::text AS memory_id,
       revision, attempts, event_type, erasure_deadline
  FROM ibex_core.memory_lifecycle_claim_erasure(
           CAST(:claim_limit AS integer),
           CAST(:lease_seconds AS double precision),
           CAST(:deadline_seconds AS double precision)
       )
"""

_REFS_SQL = """
SELECT store, locator
  FROM ibex_core.memory_artifact_refs
 WHERE org_id = CAST(:org_id AS uuid)
   AND memory_id = CAST(:memory_id AS uuid)
 ORDER BY store, locator
"""

_RECEIPTS_SQL = """
SELECT store, status
  FROM ibex_core.erasure_store_receipts
 WHERE org_id = CAST(:org_id AS uuid)
   AND memory_id = CAST(:memory_id AS uuid)
   AND revision = :revision
"""

#: The memory's agent, used only to derive the hot cache key for a row that
#: predates the cache refs. The memory row is tombstoned, not deleted, so the
#: value is still there for a forget. A missing row is a permanent failure for
#: the hot store: absence cannot be proved without the key.
_AGENT_ID_SQL = """
SELECT agent_id::text AS agent_id
  FROM ibex_core.memories
 WHERE org_id = CAST(:org_id AS uuid)
   AND id = CAST(:memory_id AS uuid)
"""

# The unique key from 000073 is the idempotency mechanism: a redelivery of the
# same (org, memory, revision, store) updates the one row instead of adding one.
# The conflict guard is monotonic: a receipt that already says ``verified`` is
# never replaced by a weaker status. The request path can write a ``failed``
# cache receipt while this sweep is settling the same revision, and a late
# failure must not overwrite the proof this run earned.
_UPSERT_RECEIPT_SQL = """
INSERT INTO ibex_core.erasure_store_receipts (
    org_id, memory_id, revision, store, status, verified_absent_at,
    idempotency_key, error
) VALUES (
    CAST(:org_id AS uuid), CAST(:memory_id AS uuid), :revision, :store, :status,
    CASE WHEN :status = 'verified' THEN NOW() ELSE NULL END,
    :idempotency_key, :error
)
ON CONFLICT (org_id, memory_id, revision, store) DO UPDATE
   SET status = EXCLUDED.status,
       verified_absent_at = EXCLUDED.verified_absent_at,
       error = EXCLUDED.error,
       idempotency_key = EXCLUDED.idempotency_key
 WHERE ibex_core.erasure_store_receipts.status <> 'verified'
    OR EXCLUDED.status = 'verified'
"""

_COMPLETE_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET erasure_state = 'complete',
       delivered_at = NOW(),
       locked_until = NULL
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
"""

_RETRY_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET erasure_state = 'partial',
       available_at = NOW() + make_interval(secs => :delay_seconds),
       locked_until = NULL
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
"""

_FAIL_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox
   SET erasure_state = 'failed',
       locked_until = NULL
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
"""

#: Settlement fence. The row is locked and the attempt this run claimed is
#: checked before any receipt is written, so a worker whose lease expired cannot
#: overwrite a newer worker's proof with its own outcome.
_CLAIM_STILL_HELD_SQL = """
SELECT id
  FROM ibex_core.memory_lifecycle_outbox
 WHERE id = CAST(:id AS uuid)
   AND org_id = CAST(:org_id AS uuid)
   AND delivered_at IS NULL
   AND attempts = CAST(:attempts AS integer)
  FOR UPDATE
"""

# A row superseded by a newer delivered revision is retired with the newer row's
# state: the erasure for this memory is whatever the newest revision proved.
_RETIRE_STALE_SQL = """
UPDATE ibex_core.memory_lifecycle_outbox AS stale
   SET delivered_at = NOW(),
       locked_until = NULL,
       erasure_state = newer.erasure_state
   FROM (
        SELECT erasure_state
          FROM ibex_core.memory_lifecycle_outbox
         WHERE org_id = CAST(:org_id AS uuid)
           AND memory_id = CAST(:memory_id AS uuid)
           AND delivered_at IS NOT NULL
           AND revision > :revision
         ORDER BY revision DESC
         LIMIT 1
       ) AS newer
 WHERE stale.id = CAST(:id AS uuid)
   AND stale.org_id = CAST(:org_id AS uuid)
   AND stale.delivered_at IS NULL
   AND stale.attempts = CAST(:attempts AS integer)
"""

_DELETE_SESSION_EVENT_SQL = """
DELETE FROM ibex_core.session_events
 WHERE org_id = CAST(:org_id AS uuid)
   AND id = CAST(:event_id AS bigint)
"""

_COUNT_SESSION_EVENT_SQL = """
SELECT count(*)
  FROM ibex_core.session_events
 WHERE org_id = CAST(:org_id AS uuid)
   AND id = CAST(:event_id AS bigint)
"""
