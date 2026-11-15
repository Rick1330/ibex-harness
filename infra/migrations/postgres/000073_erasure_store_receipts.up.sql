-- Stage 2 erasure receipts: one row per (memory, revision, store) recording
-- whether that store was verified absent for that revision of the memory.
--
-- This is the per-memory analogue of 000037's deletion_store_receipts, which is
-- keyed to an org_deletion_jobs row and therefore cannot describe a single
-- memory forget. A forget that tombstones PostgreSQL and deletes the memory's
-- object-store, ClickHouse, and session_event copies needs its own proof, or
-- "erased everywhere" is an unverified claim.
--
-- No FK on org_id or memory_id, matching 000072: the receipt must outlive the
-- organization purge and the memory row it describes, because it is the evidence
-- that the erasure happened.
--
-- Tenant boundary: org GUC only (rls_org_visible, 000063).

CREATE TABLE ibex_core.erasure_store_receipts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID NOT NULL,
    memory_id UUID NOT NULL,
    revision BIGINT NOT NULL CHECK (revision > 0),
    store TEXT NOT NULL CHECK (store IN ('postgres','clickhouse','objectstore')),
    status TEXT NOT NULL CHECK (status IN ('pending','verified','failed','not_applicable')),
    verified_absent_at TIMESTAMPTZ,
    idempotency_key TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (org_id, memory_id, revision, store)
);

-- Erasure reads and resumes the receipts of one memory inside one org.
CREATE INDEX idx_erasure_store_receipts_org_memory
    ON ibex_core.erasure_store_receipts (org_id, memory_id);

ALTER TABLE ibex_core.erasure_store_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE ibex_core.erasure_store_receipts FORCE ROW LEVEL SECURITY;
CREATE POLICY erasure_store_receipts_isolation
    ON ibex_core.erasure_store_receipts
    USING (ibex_core.rls_org_visible(org_id))
    WITH CHECK (ibex_core.rls_org_visible(org_id));

-- Same grant set as 000072, plus UPDATE: the saga reads the receipts, writes the
-- first one, and moves a receipt pending -> verified/failed in place — all as the
-- tenant. UPDATE is required because that transition is the one thing the erasure
-- proof depends on; without it the consumer could insert a row and never record
-- the outcome. No DELETE for the tenant identity: a receipt is the proof, and
-- deleting one erases the record that a store was cleared. `ibex_service` keeps
-- DELETE for operator-driven cleanup.
GRANT SELECT, INSERT, UPDATE ON ibex_core.erasure_store_receipts TO ibex_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ibex_core.erasure_store_receipts TO ibex_service;
GRANT USAGE ON SCHEMA ibex_core TO ibex_app;
GRANT USAGE ON SCHEMA ibex_core TO ibex_service;

-- `updated_at` is only meaningful if it advances; 000037 gives its sibling
-- receipts table the same trigger.
CREATE TRIGGER erasure_store_receipts_updated_at
    BEFORE UPDATE ON ibex_core.erasure_store_receipts
    FOR EACH ROW EXECUTE FUNCTION ibex_core.set_updated_at();

COMMENT ON TABLE ibex_core.erasure_store_receipts IS
    'Per-memory, per-revision, per-store proof that a memory forget reached and removed (or found nothing in) that store.';
COMMENT ON COLUMN ibex_core.erasure_store_receipts.verified_absent_at IS
    'Set only when the store confirmed the memory is absent; NULL while pending, failed, or not_applicable.';
COMMENT ON COLUMN ibex_core.erasure_store_receipts.idempotency_key IS
    'Caller-supplied key that makes a retried store erasure reuse the existing receipt instead of writing a second one.';
