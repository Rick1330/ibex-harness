-- A receipt records the addresses its proof covered, not merely that "the store"
-- was cleared.
--
-- Why this exists: `erasure_store_receipts` recorded
-- `(org_id, memory_id, revision, store, status)` and nothing about which locator
-- the proof covered. `_receipt_already_proves` returned true for any `verified`
-- receipt regardless of the current locators, and only the object store was
-- re-observed on a retry. So a copy recorded at a *new* address between two
-- sweeps of the same revision — a new `session_event` row, a different archive
-- key, a ClickHouse event id — was never staged: the second sweep settled on the
-- earlier receipt and the row completed while the copy at that new address
-- survived.
--
-- What coverage does not close: the `cache` locator (`{org}:memory:{id}`) and
-- the `cache_hot` locator (`{org}:hot_memories:{agent_id}`) are fixed keys written
-- once, in the forget transaction. A value re-populated at one of those keys
-- after its delete reuses the *identical* locator, so it stays inside the
-- receipt's coverage and this gate settles the store over it. That is a
-- different phenomenon with a different fence — the forgotten marker and the
-- ZREM-before-check ordering — and it remains an open residual, not a gap this
-- migration closes.
--
-- `covered_addresses` is the locator set the receipt's proof covered. NULL means
-- "covers no address", never "covers everything": every receipt written before
-- this migration is treated as covering nothing, so a retry stages the store
-- again rather than certifying an address the earlier run never saw. There is no
-- backfill because the old rows do not record what they erased, and inventing a
-- coverage set would be a false proof.
--
-- Deliberately nullable with no default. Six seeding sites insert an explicit
-- column list; a NOT NULL would reject them and force a fabricated value. The
-- `store` domain is untouched.
--
-- Forward-only (ADR-0098): the down refuses while any receipt carries a coverage
-- set, because dropping the column would delete the only record of which
-- addresses a proof covered.
--
-- `lock_timeout` is `SET`, not `SET LOCAL`, and is reset at the end. The whole
-- file is one implicit transaction — golang-migrate passes it to a single
-- zero-argument `ExecContext`, which lib/pq sends as one simple-query message, so
-- the statements are atomic — but it is not a transaction *block*: `SET LOCAL` is
-- honoured only while the message holds more than one statement and warns "SET
-- LOCAL can only be used in transaction blocks" otherwise (measured on 16.15).
-- `SET` is session scope and survives that commit, hence the `RESET`: the driver
-- reuses one connection for consecutive steps. `ADD COLUMN` takes ACCESS
-- EXCLUSIVE on a table the erasure worker writes continuously, so the wait is
-- bounded (same intent as 000063:30 and 000075:28) instead of queueing readers
-- behind the worker's lock.

SET lock_timeout = '5s';

ALTER TABLE ibex_core.erasure_store_receipts
    ADD COLUMN covered_addresses TEXT[];

COMMENT ON COLUMN ibex_core.erasure_store_receipts.covered_addresses IS
    'Artifact locators this receipt''s proof covered. NULL means it covers no address (a pre-000080 receipt, or one that proved nothing), so a retry stages the store again rather than certifying an unseen copy.';

RESET lock_timeout;
