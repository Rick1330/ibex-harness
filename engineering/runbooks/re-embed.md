# Runbook: re-embed the memory corpus onto a new embedding model

**Status:** `provisional`. Steps 2, 5, and 6 need code that does not exist in this repository today — no generation
column, no backfill task, and no per-generation index. The model id is configurable and search accepts an optional model
fence, but the fence is off by default and filters one HNSW candidate set rather than routing to a generation's index.
Step 0 is a configuration precondition that must be satisfied before any switch regardless. Do not run the procedure
against a shared deployment until the missing pieces are implemented and tested; this file is the design of record for
building them, not evidence that they work.

**Identity source of truth:** [`engineering/MODEL_INVENTORY.md`](../MODEL_INVENTORY.md) and
`infra/model-inventory.v1.json`.

## When to use this

- The weights revision changes under an unchanged model id (a TEI `--revision` bump, a provider snapshot change).
- The model id changes (for example `BAAI/bge-m3` → another 1024-dimension model).
- A dimension change is *not* covered: `memories.embedding` is `vector(1024)` with a check constraint requiring
  `embedding_dim = 1024` (`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:13-16,36-45`), so a switch to
  384 or 3072 dimensions is a schema migration plus a full table rewrite, not a backfill. Treat it as a separate change.

## Why a switch is not a config edit

Vectors from two models are not comparable: `engineering/adr/0046-embedder-interface-registry.md:22` records that mixing
them in one index yields silent bad recall rather than a hard error. The current tree records a configurable model id on
every embedded row (`services/memory/app/config.py:160-180,426-436`) and search accepts an optional `embedding_model`
fence (`services/memory/app/schemas/search.py:19-48`,
`services/memory/app/vectorstore/pgvector_store.py:16-50`), but the fence is off by default and is a post-filter over the
HNSW candidate set, not a per-generation index. A second generation therefore still shares one index and one unfenced
default result set; re-verify this against the tree you are working in, because it is the part of the record most likely
to have moved.

## Preconditions

1. **A pinned identity.** The new model id, its revision, and its licence are recorded in `MODEL_INVENTORY.md` and the
   JSON twin, and the deployment is pinned to that revision (Compose `--revision` for TEI, a snapshot parameter for a
   hosted provider). A generation you cannot name is not a generation you can roll back to.
2. **Provenance is written, not assumed.** The write path records the configured model id
   (`services/memory/app/config.py:160-180,426-436`; `services/memory/app/write/orchestrator.py:76,262-273`;
   `services/memory/app/write/after_commit.py:23-26,50`), not a hard-coded literal. What it does not record is the
   embedder's reported `model_id`: `services/memory/app/write/factory.py:85-92` drops `result.model_id` from the
   response (`services/memory/app/clients/embedding.py:79,276-281`). The stored value is the operator's claim, so the
   backfill must set it deliberately and cannot rely on the process to verify it against the model that actually
   produced the vector.
3. **A rollback generation stays intact.** Nothing in the procedure below overwrites the old vectors until the new
   generation is verified.
4. **Traffic window.** The backfill runs at write-rate priority, not at latency priority: the embedder is the same
   process the write path calls, and TEI in `v1-single-node` is CPU-bound (`engineering/DEPLOYMENT.md:129-134`).

## Procedure

### Step 0 — configure the revision, or the cache cannot tell the weights apart

`content_digest` hashes `(model_id, dimensions, [revision], text)` through `EmbeddingIdentity`
(`services/embedder/app/cache/keys.py:13-55`), and the cache resolves the backend's `model_id`, `dimensions` and
`model_revision` into that identity once (`services/embedder/app/cache/backend.py:97-105`).

- If the id changes, the digest changes with it and the cache is correct by construction.
- The revision is hashed **only when it is non-empty**. Set `IBEX_EMBEDDING_MODEL_REVISION`
  (`services/embedder/app/config.py`) to the same revision the deployment pins (`--revision` for TEI) before the first
  write against the new weights. Configuring it changes every digest, so existing entries become misses and recompute
  from the new weights rather than being served as if they came from them.
- If the revision is left unset, the byte layout stays identical to the pre-revision digest: two deployments that differ
  only in weights share cached vectors for the TTL. Nothing compares `--revision` to `IBEX_EMBEDDING_MODEL_REVISION`, so
  this pairing is the operator's obligation. The fallback is to purge `{org_id}:embed:v1:*` for every organization
  before the first write against the new backend.

The failure mode here is silent: the vectors look valid and the recall loss appears only in retrieval quality.

### Step 1 — record the new model id and revision

Write the id, revision, and licence into `engineering/MODEL_INVENTORY.md` and `infra/model-inventory.v1.json` in the same
commit that pins the deployment. Bump the inventory's `recorded_at`. Nothing about the switch is auditable without this
row.

Two enforcement details decide the deploy order:

- The embedder refuses readiness when the TEI `/info` `model_id` or the reported dimensions differ from its configured
  pair (`services/embedder/app/main.py:97-113`). `IBEX_EMBEDDING_MODEL` and the server's `--model-id` must therefore move
  together, or the service stays unready.
- That check compares the model id only. It cannot tell two revisions of the same id apart, so a revision bump is
  invisible to readiness and to the cache (Step 0).

### Step 2 — dual-write the new generation

Add a second generation alongside the current one; do not overwrite it.

```sql
-- Sketch, not a migration: this column does not exist today.
ALTER TABLE ibex_core.memories
    ADD COLUMN embedding_next vector(1024),
    ADD COLUMN embedding_next_model TEXT,
    ADD COLUMN embedding_next_revision TEXT;
```

Dual-write means every *new* memory is embedded by both paths, or by the new model only plus a backfill job for the old
one. The cheaper shape is new-writes-new-model plus a backfill for the existing corpus; it is also the one that keeps the
reader correct, because the reader still reads the old column until the cut-over in Step 6. Whichever shape is chosen,
readers keep reading the old generation for the whole window — that is what makes Step 7 a revert rather than a
re-embed.

### Step 3 — batched backfill

Client caps, enforced in `services/embedder/app/limits.py:3-4`:

- `MAX_BATCH_TEXTS = 64` — at most 64 texts per request.
- `MAX_TEXT_BYTES = 32 * 1024` — at most 32 KiB per text.

Batching rules:

1. Select by keyset on `id`, not by offset: `WHERE org_id = :org AND id > :last_id ORDER BY id LIMIT :n`. A restart then
   costs at most one batch.
2. Chunk to at most 64 texts per request. A request at the byte cap holds at most 2 MiB of text (64 × 32 KiB); size the
   batch down from there for the CPU-bound backend.
3. Read one text at a time from the database; never hold 64 full texts in memory per concurrent worker beyond what the
   request needs.
4. Skip rows that are not visible to users: `tombstoned`, `deleted_at IS NOT NULL`, `status <> 'active'`, and rows that
   failed a forget. Re-embedding a tombstoned row is wasted work, and forgetting already nulls the embedding
   (`services/memory/app/lifecycle.py:134`).

### Step 4 — per-row read → embed → CAS upsert with `expected_revision`

The write already exists and must be reused rather than reimplemented. `PgVectorStore.upsert`
(`services/memory/app/vectorstore/pgvector_store.py:64-96`) updates the vector only when the row still matches the
revision that was read:

```sql
UPDATE ibex_core.memories
   SET embedding = CAST(:embedding AS vector),
       embedding_model = :embedding_model,
       embedding_dim = :embedding_dim,
       updated_at = NOW()
 WHERE id = :memory_id
   AND org_id = :org_id
   AND deleted_at IS NULL
   AND tombstoned = FALSE
   AND status <> 'deleted'
   AND lifecycle_revision = :expected_revision
```

`UpsertRequest` carries `expected_revision` and rejects a non-positive value
(`services/memory/app/vectorstore/base.py:26-45`), and `rowcount != 1` raises `LookupError`
(`services/memory/app/vectorstore/pgvector_store.py:94-96`).

Per row:

1. Read `id`, `content`, and `lifecycle_revision`.
2. Embed the text (Step 3 caps).
3. Upsert against the generation column with the revision that was read.
4. On `LookupError`, do not retry blindly: the row was superseded, tombstoned, forgotten, or deleted between the read and
   the write. Count it as skipped and let the next pass see the new revision. Writing with a stale revision would
   resurrect an embedding on a row a legal hold is trying to erase.

CAS is not optional here: the memory service's own write path uses the same fence, so the backfill competes with live
writes on the same rows.

### Step 5 — index per generation during the window

The vector index is a single partial HNSW index on `embedding`
(`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:95-97`). During the window the new generation needs its
own index, or the query planner has nothing to search:

```sql
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_memories_embedding_next_hnsw
    ON ibex_core.memories
    USING hnsw (embedding_next vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE status = 'active' AND deleted_at IS NULL;
```

- `CONCURRENTLY` is mandatory under write load; the precedent and its caveat are in
  `infra/migrations/postgres/000011_sessions_idle_sweep_index.up.sql:2-4` — a failed concurrent build leaves an invalid
  index that must be dropped and retried.
- Create the index **before** the backfill fills the column, not after: an HNSW build over an already-populated column is
  the long pole, and the index can be built incrementally from an empty column.
- Do not add a model filter to the existing index instead. A partial index is per-generation by construction; a predicate
  added afterwards does not exist.
- Match the `m` and `ef_construction` values to the existing index (16 and 64) so the two generations are measured under
  the same construction parameters.

### Step 6 — cut over the search filter, only after the backfill completes

**Gate:** the backfill is complete when the count of visible rows with a null or old-generation `embedding_next` is zero
for every organization. Check that count; do not infer completion from a job log.

Only then change the reader to the new column and generation. The reason for the order is the index, not convenience: an
HNSW scan returns its top-k candidates before any predicate on a non-indexed column is applied, so a "filter by
`embedding_model`" applied after the scan shrinks the result set below `LIMIT` and loses recall for exactly the rows that
are not yet backfilled. Ordering the filter after a complete backfill means there is nothing left to drop. pgvector 0.8+
exposes iterative scan (`off` / `relaxed_order` / `strict_order`, see the comment at
`services/memory/app/vectorstore/base.py:81-84`) as the mitigation when a filtered scan is unavoidable; it buys recall
with latency and is not a substitute for the gate above.

Sequence:

1. Deploy the reader that filters on the new generation, with the old column still populated.
2. Verify retrieval on a known query set before dropping anything (Step 7).
3. Only then drop the old index and the old column, in a later change.

### Step 7 — verify

- Counts: rows with the new generation = visible rows; rows with both generations = 0; rows with neither = 0.
- Retrieval: the same query set returns the same neighbours from the new generation as from the old, within the recall
  agreement the ranking gate already measures (`engineering/adr/0061-retrieval-quality-benchmark-methodology.md`). A
  generation that changes neighbours without a quality gain is a regression, not a migration.
- Errors: no `LookupError` storm in the backfill log (a storm means live writes are racing the pass), and no
  `embedding_dim` check violation.
- Cache: the old namespace is either purged or unreachable by the new model id.

### Rollback

Rollback is a revert, not a re-embed, and that is the point of Steps 2 and 6:

1. Point the reader back at the old column. One query change and one deploy; no data is written.
2. Leave the new generation in place. It is inert until a reader uses it, and dropping it destroys the only copy of work
   that may take hours to redo.
3. If the switch also changed `IBEX_EMBEDDING_MODEL`, revert it in the same change as the reader, or the write path will
   keep producing the new generation into a column nothing reads.
4. Purge the cache namespace for the abandoned model id, or a later switch back will serve vectors from the abandoned
   generation.

The one case with no clean revert is a *dimension* change, which is why it is out of scope above: the column type moves,
and going back is a second table rewrite.

## What is missing today, and what that costs

Every bullet here describes the current tree; re-verify before you rely on one.

- **No job ledger.** No table records which rows a pass has completed. A restart redoes the batch it was in and
  everything after the last checkpoint it did not persist; the work is idempotent (the CAS upsert writes the same
  generation for the same revision) but it is not resumable, so a large corpus costs the full pass again after an
  interruption. Keyset pagination (Step 3) bounds the loss to one batch; a ledger would remove it. Do not invent one here.
- **No generation column, no backfill task, no per-generation index.** `ibex.worker.embedding.noop` is the only
  embedding task (`services/worker/app/task_names.py:5,18`). `SearchRequest` carries an optional `embedding_model`
  fence (`services/memory/app/vectorstore/base.py:58-108`), but it defaults to off and filters one HNSW candidate set;
  Steps 2, 5, and 6 are designs until a generation column, a backfill task, and a per-generation index land.
- **Provenance is a claim, not a measurement.** The row records the configured `IBEX_MEMORY_EMBEDDING_MODEL`
  (`services/memory/app/config.py:160-180`), not the embedder's reported `model_id`
  (`services/memory/app/write/factory.py:85-92`), so a mis-set id labels every generation identically and the cut-over
  cannot be verified from the model column alone. Verify by sampling vectors against the pinned backend.
- **Worker failures are stored, not dropped.** `ibex_core.failed_tasks` keeps `args`, `kwargs`, `exception_message`, and
  `traceback` (`infra/migrations/postgres/000021_create_failed_tasks.up.sql:7-13`) and has no row-level security and no
  prune. Pass memory ids only — never the text — so a failed batch does not become a content store.
- **The reranker is not part of this procedure.** Its identity is not recorded at all; see
  `engineering/MODEL_INVENTORY.md` § 3. Changing it changes ranking, not stored vectors, and does not require a backfill.

## Related

- `engineering/MODEL_INVENTORY.md` — the inventory this procedure updates.
- `infra/model-inventory.v1.json` — the machine-readable twin.
- `engineering/architecture-v2/27-v1-readiness-audit.md` — P1-30 (no version filtering, no re-embed runbook) and P1-31
  (no provenance inventory).
- ADR-0046 (`engineering/adr/0046-embedder-interface-registry.md`) — profiles, and why dimensions are not interchangeable.
- ADR-0061 (`engineering/adr/0061-retrieval-quality-benchmark-methodology.md`) — the recall gate Step 7 reuses.
