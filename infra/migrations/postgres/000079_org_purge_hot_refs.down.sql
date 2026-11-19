-- Roll back the purge's hot-ref provenance grant.
--
-- The rows 000079 allowed `ibex_purge` to write are ordinary
-- `memory_artifact_refs` rows; they are the erasure consumer's worklist and
-- nothing here deletes them. Revoking the grant only stops the saga recording
-- new addresses; existing rows stay readable by `ibex_erasure` (000075). The
-- comment is restored to the 000072 text so an up after this down reads the
-- table the way the older migration described it.

REVOKE INSERT (org_id, memory_id, store, locator)
    ON ibex_core.memory_artifact_refs FROM ibex_purge;

REVOKE SELECT (agent_id) ON ibex_core.memories FROM ibex_purge;

COMMENT ON TABLE ibex_core.memory_artifact_refs IS
    'Write-time provenance: one row per (memory, external store, locator), so a memory forget can reach and prove deletion of its object-store, ClickHouse, and session_event copies.';
