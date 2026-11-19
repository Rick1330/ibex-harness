-- The Redis cache is a fifth and sixth store a memory forget must prove, and the
-- request path may record its own failed attempt without gaining proof authority.
--
-- Why this exists: `POST /v1/memories/{id}/forget` tombstoned PostgreSQL, the
-- object-store archive, the ClickHouse evidence and the `session_events` row, but
-- its cache eviction was best-effort: `MemoryCacheWriter.forget_memory` swallowed
-- Redis errors, `invalidate_forgotten_memory` logged a warning and returned, and
-- nothing recorded that a content-bearing cache entry might still be served. A
-- cached memory object holds the memory's full `content` for up to
-- `memory_cache_ttl_seconds` (3600 s by default), so a failed eviction is a
-- disclosure that "forgotten" did not describe.
--
-- Two stores, not one, because the two Redis structures have different purge
-- semantics and one verb cannot serve both:
--   * `cache`     — the object cache entry `{org}:memory:{memory}`: a JSON string
--                   holding the content. Purged with DEL.
--   * `cache_hot` — the per-agent hot sorted set `{org}:hot_memories:{agent}`:
--                   membership plus a score, no content. Purged with ZREM of the
--                   one member, never DEL of the key, which would evict every
--                   other memory's hot score for that agent.
-- Naming them separately keeps the receipt honest about which structure was
-- cleared and lets the consumer apply the right verb without guessing from a key
-- string. The store name is the contract; a locator never encodes an operation.
--
-- Both domains are widened on `memory_artifact_refs` as well: the forget
-- transaction records the two addresses in the same transaction as the tombstone,
-- so the consumer can reach them even if the request path dies before it evicts.
-- A ref is the address; the receipt is the proof.
--
-- Who may write what. 000075 deliberately revoked INSERT/UPDATE on
-- `erasure_store_receipts` from `ibex_app`, because a tenant identity that can
-- write a receipt can forge `verified` for a store it never cleared. That
-- boundary stands: this migration grants the tenant no proof write. Instead the
-- outbox row gets one tenant-writable *attempt* column, and its domain has no
-- `verified` value at all:
--   * `cache_eviction_state` — `pending` (no request-path failure recorded) or
--     `failed` (the request path exhausted its retries). The tenant can only
--     report that work is outstanding; it cannot report that absence was proved.
--   * `cache_eviction_error` — a short, content-free reason for the failed state.
-- The forget response maps a store to `failed` from this column only while no
-- receipt exists; a worker receipt always wins. The proof stays worker-only.
--
-- Forward-only (ADR-0098): the down file refuses while any cache receipt, cache
-- ref, or failed attempt exists, because the narrowed CHECK cannot hold it and
-- deleting it to make the rollback succeed would delete evidence.

ALTER TABLE ibex_core.erasure_store_receipts
    DROP CONSTRAINT erasure_store_receipts_store_check;
ALTER TABLE ibex_core.erasure_store_receipts
    ADD CONSTRAINT erasure_store_receipts_store_check
    CHECK (store IN (
        'postgres','clickhouse','objectstore','session_event','cache','cache_hot'
    ));

ALTER TABLE ibex_core.memory_artifact_refs
    DROP CONSTRAINT memory_artifact_refs_store_check;
ALTER TABLE ibex_core.memory_artifact_refs
    ADD CONSTRAINT memory_artifact_refs_store_check
    CHECK (store IN (
        'objectstore','clickhouse','session_event','cache','cache_hot'
    ));

-- Deliberately no `verified` state: the tenant records work, never proof.
ALTER TABLE ibex_core.memory_lifecycle_outbox
    ADD COLUMN cache_eviction_state TEXT NOT NULL DEFAULT 'pending'
        CHECK (cache_eviction_state IN ('pending','failed')),
    ADD COLUMN cache_eviction_error TEXT;

-- Column-scoped, in the 000064/000074 style: the tenant may update the two
-- attempt columns and nothing else. The settle columns stay with `ibex_erasure`
-- (000075), so this grant cannot widen into a proof or a delivery write.
GRANT UPDATE (cache_eviction_state, cache_eviction_error)
    ON ibex_core.memory_lifecycle_outbox TO ibex_app;

COMMENT ON COLUMN ibex_core.erasure_store_receipts.store IS
    'Store whose absence was checked for this memory revision: postgres, clickhouse, objectstore, session_event, cache (object cache entry), or cache_hot (hot sorted-set membership).';
COMMENT ON COLUMN ibex_core.memory_artifact_refs.store IS
    'Store the locator addresses: objectstore, clickhouse, session_event, cache (object cache entry), or cache_hot (hot sorted-set membership).';
COMMENT ON COLUMN ibex_core.memory_lifecycle_outbox.cache_eviction_state IS
    'Request-path cache eviction attempt: pending (no failure recorded) or failed (retries exhausted). Never a proof of absence; receipts are worker-only.';
COMMENT ON COLUMN ibex_core.memory_lifecycle_outbox.cache_eviction_error IS
    'Content-free reason for a failed request-path cache eviction; null otherwise.';
