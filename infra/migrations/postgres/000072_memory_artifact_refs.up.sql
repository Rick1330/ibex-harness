-- Stage 2 erasure provenance: the durable link from a memory to the copies of it
-- that live outside PostgreSQL — object-store capture archives, ClickHouse
-- evidence, and session_events rows.
--
-- Why a table instead of a lookup: nothing else in the schema records which
-- archive object or which session event carried a given memory. A forget can
-- tombstone the memory row and emit a lifecycle outbox event (000045), but
-- without this row the S3 object and the ClickHouse evidence are unreachable.
-- Provenance cannot be reconstructed after the fact, so it is written at the
-- moment the copy is written.
--
-- No FK on org_id or memory_id, for the same reason as 000045: an org purge
-- deletes the organization and its memories, and the refs must outlive that
-- deletion — they are the worklist that drives, and the record that proves, the
-- erasure of the external copies. A cascade would delete the worklist with the
-- thing it points at.
--
-- Tenant boundary: org GUC only (rls_org_visible, 000063). No service-account
-- GUC is trusted, so a tenant cannot write or read another tenant's refs.

CREATE TABLE ibex_core.memory_artifact_refs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     UUID NOT NULL,
    memory_id  UUID NOT NULL,
    store      TEXT NOT NULL CHECK (store IN ('objectstore','clickhouse','session_event')),
    locator    TEXT NOT NULL CHECK (char_length(locator) BETWEEN 1 AND 1024),
    session_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, memory_id, store, locator)
);

-- Erasure reads every ref of one memory inside one org.
CREATE INDEX idx_memory_artifact_refs_org_memory
    ON ibex_core.memory_artifact_refs (org_id, memory_id);

ALTER TABLE ibex_core.memory_artifact_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.memory_artifact_refs FORCE ROW LEVEL SECURITY;
CREATE POLICY memory_artifact_refs_isolation
    ON ibex_core.memory_artifact_refs
    USING (ibex_core.rls_org_visible(org_id))
    WITH CHECK (ibex_core.rls_org_visible(org_id));

-- The capture archiver writes refs as ibex_app inside the tenant transaction.
-- SELECT and INSERT only, no DELETE: a ref is the only address of an external
-- copy, and deleting it makes every store it names look like "not_applicable" on
-- the next erasure — a one-statement bypass of the proof the erasure exists to
-- produce. A verified erasure deliberately keeps its ref: the receipt is the
-- proof and the ref is the address the proof refers to, so there is nothing to
-- retire. `ibex_service` keeps DELETE for operator-driven cleanup, which is the
-- only caller that has one.
GRANT SELECT, INSERT ON ibex_core.memory_artifact_refs TO ibex_app;
GRANT SELECT, INSERT, DELETE ON ibex_core.memory_artifact_refs TO ibex_service;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_service;

COMMENT ON TABLE ibex_core.memory_artifact_refs IS
    'Write-time provenance: one row per (memory, external store, locator), so a memory forget can reach and prove deletion of its object-store, ClickHouse, and session_event copies.';
COMMENT ON COLUMN ibex_core.memory_artifact_refs.locator IS
    'Store-native address: an object-store URI, a ClickHouse evidence key, or the session_events.id of the capture (as text).';
COMMENT ON COLUMN ibex_core.memory_artifact_refs.session_id IS
    'Session of the capture event the ref was written from, when there is one.';
