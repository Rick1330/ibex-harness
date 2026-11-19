-- The organization purge records each memory's hot-cache address before it
-- deletes the memory row.
--
-- Why this exists: the saga's Redis stage deletes every `{org}:hot_memories:*`
-- key and records a `verified` receipt, but a receipt proves only that the
-- org-wide delete *ran*. A create can commit and its after-commit `refresh_hot`
-- can land after that delete; with no forgotten marker and no address, the
-- memory-lifecycle erasure consumer had nothing to `ZREM` and could settle the
-- row `complete` on the receipt while the member survived to its TTL
-- (`_org_purge_outcome`, PR #1260 review).
--
-- The fix is provenance, not a stronger receipt: `_stage_postgres` now inserts
-- one `memory_artifact_refs` row per memory (`store = 'cache_hot'`,
-- `locator = '<org>:hot_memories:<agent>'`) in the same transaction as the
-- `DELETE FROM memories`. The ref has no FK to `memories` (000072), so it
-- outlives the delete by design. The consumer stages that address like any
-- other: forgotten marker first, then `ZREM`, then verify absent — and the
-- marker is what fences the delayed write.
--
-- Grants: the saga runs as `ibex_purge` (000064, `session_as_purge_org`). It
-- needs the memory's agent to build the locator, and INSERT on the four ref
-- columns. It gets no SELECT, UPDATE or DELETE on the refs table: a ref is the
-- consumer's worklist, and the purge identity must not be able to erase one and
-- make a store look `not_applicable`. Both grants are column-scoped; neither
-- exposes memory content.

GRANT SELECT (agent_id) ON ibex_core.memories TO ibex_purge;

GRANT INSERT (org_id, memory_id, store, locator)
    ON ibex_core.memory_artifact_refs TO ibex_purge;

COMMENT ON TABLE ibex_core.memory_artifact_refs IS
    'Write-time provenance: one row per (memory, external store, locator), so a memory forget can reach and prove deletion of its object-store, ClickHouse, session_event, and cache copies. The organization purge writes the cache_hot row before it deletes the memory.';
