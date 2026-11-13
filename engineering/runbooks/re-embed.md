# Runbook: re-embed the memory corpus onto a new embedding model

**Status:** `provisional`. Steps 2, 4, 5, and 6 need code that does not exist in this repository today — no generation
column, no generation-aware write, no backfill task, and no per-generation index. The recorded identity is configurable
— `<model_id>`, or `<model_id>@<revision>` when the revision is set (`services/memory/app/config.py:428-465`) — and
search accepts an optional fence carrying that identity, but the fence is off by default, is a post-filter over one HNSW
candidate set rather than a route to a generation's index, and bounds **vector candidates only**: full-text results are
not fenced. Step 0 is a configuration precondition that must be satisfied before any switch regardless. Do not run the
procedure against a shared deployment until the missing pieces are implemented and tested; this file is the design of
record for building them, not evidence that they work.

**Identity source of truth:** [`engineering/MODEL_INVENTORY.md`](../MODEL_INVENTORY.md) and
`infra/model-inventory.v1.json`.

## When to use this

- The weights revision changes under an unchanged model id (a TEI `--revision` bump, a provider snapshot change).
- The model id changes (for example `BAAI/bge-m3` → another 1024-dimension model).
- A dimension change is *not* covered: `memories.embedding` is `vector(1024)` with a check constraint requiring
  `embedding_dim = 1024` (`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:13-15,27-38`), so a switch to
  384 or 3072 dimensions is a schema migration plus a full table rewrite, not a backfill. Treat it as a separate change.

## Why a switch is not a config edit

Vectors from two models are not comparable: `engineering/adr/0046-embedder-interface-registry.md:22` records that mixing
them in one index yields silent bad recall rather than a hard error. The current tree records a configurable identity on
every embedded row (`services/memory/app/config.py:164-184,428-465`): the model id, or `id@revision` when
`IBEX_MEMORY_EMBEDDING_MODEL_REVISION` is set, compared byte-identically. Search accepts an optional `embedding_model`
fence that must be given that same full string (`services/memory/app/schemas/search.py:19-52`,
`services/memory/app/vectorstore/pgvector_store.py:27-51,209-229`), but the fence is off by default, is a post-filter
over one HNSW candidate set rather than a per-generation index, and is applied to the vector channel only: the full-text
supplement and the hybrid full-text channel score by `ts_rank_cd` and are not fenced
(`services/memory/app/read/repository.py:206-211`). A second generation therefore still shares one index, one unfenced
default result set, and unfenced keyword results; re-verify this against the tree you are working in, because it is the
part of the record most likely to have moved.

## Preconditions

1. **A pinned identity.** The new model id, its revision, and its licence are recorded in `MODEL_INVENTORY.md` and the
   JSON twin, and the deployment is pinned to that revision (Compose `--revision` for TEI, a snapshot parameter for a
   hosted provider). A generation you cannot name is not a generation you can roll back to.
2. **Provenance is written, not assumed.** The write path records the configured identity
   (`services/memory/app/config.py:164-184,428-465`; `services/memory/app/write/orchestrator.py:76,261-274`;
   `services/memory/app/write/after_commit.py:23-26,50`), not a hard-coded literal. The value is the model id, or
   `id@revision` when `IBEX_MEMORY_EMBEDDING_MODEL_REVISION` is set; `@` is a separator inside one opaque string, so two
   generations are told apart by a whole-string comparison and nothing parses the revision out of it. What it does not
   record is the embedder's reported `model_id`: `services/memory/app/write/factory.py:85-92` drops `result.model_id`
   from the response (`services/memory/app/clients/embedding.py:79,276-281`). The stored value is the operator's claim,
   so the backfill must set it deliberately and cannot rely on the process to verify it against the model that actually
   produced the vector.
3. **A rollback generation stays intact.** Nothing in the procedure below overwrites the old vectors until the new
   generation is verified, and Step 2 keeps filling the old generation for rows created during the window — not only for
   the corpus that existed when the backfill started.
4. **Traffic window.** The backfill runs at write-rate priority, not at latency priority: the embedder is the same
   process the write path calls, and TEI in `v1-single-node` is CPU-bound (`engineering/DEPLOYMENT.md:129-134`).

## Procedure

### Step 0 — configure the revision, or the cache cannot tell the weights apart

`content_digest` hashes `(model_id, dimensions, [revision], text)` through `EmbeddingIdentity`
(`services/embedder/app/cache/keys.py:13-56`), and the cache resolves the backend's `model_id`, `dimensions` and
`model_revision` into that identity once (`services/embedder/app/cache/backend.py:76-87`).

- If the id changes, the digest changes with it and the cache is correct by construction.
- The revision is hashed **only when it is non-empty**. Set `IBEX_EMBEDDING_MODEL_REVISION`
  (`services/embedder/app/config.py:43-52`) to the same revision the deployment pins (`--revision` for TEI) before the
  first write against the new weights. Configuring it changes every digest, so existing entries become misses and
  recompute from the new weights rather than being served as if they came from them.
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
  pair (`services/embedder/app/main.py:85-86,96-113`). `IBEX_EMBEDDING_MODEL` and the server's `--model-id` must
  therefore move together, or the service stays unready.
- That check compares the model id only. It cannot tell two revisions of the same id apart, so a revision bump is
  invisible to readiness. The cache distinguishes it only if `IBEX_EMBEDDING_MODEL_REVISION` is configured (Step 0), and
  nothing compares that setting to `--revision`.

### Step 2 — dual-write the new generation

Add a second generation alongside the current one; do not overwrite it.

```sql
-- Sketch, not a migration: these columns do not exist today.
ALTER TABLE ibex_core.memories
    ADD COLUMN embedding_next vector(1024),
    ADD COLUMN embedding_next_model TEXT;
-- `embedding_next_model` holds one identity string, `id` or `id@revision`, mirroring
-- `embedding_model` (services/memory/app/config.py:428-465). A partial write is refused
-- by a check constraint modelled on memories_embedding_triplet_chk
-- (infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:29-39).
```

**Which column holds which generation.** Until Step 6, `embedding` / `embedding_model` / `embedding_dim` hold the
**current** (old) generation under the current identity, and `embedding_next` / `embedding_next_model` hold the **next**
generation under the next identity. The reader is the query in
`services/memory/app/vectorstore/pgvector_store.py:27-51`; it reads `embedding` and knows nothing about
`embedding_next`. At Step 6 the reader moves to `embedding_next`, and the next identity is then what a fence must carry.

**Every new memory keeps both generations.** The shape to reject is "new writes produce the new model only, plus a
backfill of the existing corpus". It cannot keep the reader correct: the reader uses the current column until Step 6, a
memory created during the window would have no current-generation vector at all, and a backfill of the corpus that
existed when it started cannot cover a row that does not exist yet. Concretely, such a row either has nothing in
`embedding` (invisible to the reader) or, if the new model writes into `embedding`, a vector recorded under the new
identity, which a current-generation fence excludes and which leaves two incomparable generations in one column when
nothing fences it. That is the silent-recall failure this runbook exists to avoid, and the window has no fixed end, so
the affected rows do not age out. What works is either shape that fills both columns for every row:

- **Dual-write both generations** on every write: one embed call per backend, both columns written.
- **Keep writing the current generation** exactly as today, and **additionally fill the next one** for the same row.

Only stop maintaining the current generation after cut-over has been verified and Step 7 has passed — not before, and
not merely because the backfill reported completion. The current generation is the rollback copy; the moment it stops
being maintained, rollback becomes a re-embed of everything written since.

Three properties of the tree make this an implementation, not a configuration change:

- The write path embeds once per memory with the process-configured backend
  (`services/memory/app/write/factory.py:85-92`) and writes one vector through `AfterCommitHandler`
  (`services/memory/app/write/after_commit.py:42-53`). `EmbedRequest` carries only `texts` and `org_id`
  (`services/embedder/app/schemas.py:31-33`; `services/memory/app/clients/embedding.py:142`), so one embedder process
  serves one generation. Two generations per new memory therefore need a second embedder deployment (or a second route)
  and a second embed call: nothing in the tree selects a model per request.
- The column is hard-coded. `PgVectorStore.upsert` sets `embedding`, `embedding_model`, `embedding_dim`
  (`services/memory/app/vectorstore/pgvector_store.py:74-77`), so the identity setting alone cannot redirect a write.
  Identity and column have to move together, which is why Step 4 needs a statement that names both.
- Moving `IBEX_MEMORY_EMBEDDING_MODEL` / `IBEX_MEMORY_EMBEDDING_MODEL_REVISION`
  (`services/memory/app/config.py:164-184`) to the new generation here would be the same bug in another place: the live
  writer would overwrite `embedding` with new-generation vectors under a new identity while the reader still reads that
  column. Moving them belongs to the cut-over (Step 6), and even there the writer has to keep stamping the current
  identity on the current column until rollback is withdrawn: a process setting names one generation, so the writer that
  maintains two has to carry both identities explicitly.

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
   (`services/memory/app/lifecycle.py:133-135`). That nulling covers `embedding`, `embedding_model`, and `embedding_dim`
   only: once a second generation exists, a forget must clear `embedding_next` and `embedding_next_model` too, or a
   forgotten row keeps a readable vector in a column the erasure code does not know about. `PgVectorStore.delete` has the
   same gap (`services/memory/app/vectorstore/pgvector_store.py:169-181`). Both are missing code, not a step here.

### Step 4 — per-row read → embed → CAS upsert with `expected_revision`

The existing write covers the **current** generation only. Reuse it for that column rather than reimplementing it.
`PgVectorStore.upsert` (`services/memory/app/vectorstore/pgvector_store.py:65-97`) sets exactly `embedding`,
`embedding_model`, `embedding_dim`, and `updated_at` (`:74-77`) and updates the row only when it still matches the
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

It never names `embedding_next*`, and it cannot be pointed at it: running this statement during the backfill would
overwrite the vectors the reader is still using and leave the next column empty. The backfill therefore needs a second
statement — the same CAS write, retargeted at the next-generation columns. Sketch, not implemented; no such method exists
today:

```sql
-- Sketch, not a method in the tree: the current upsert cannot write these columns.
UPDATE ibex_core.memories
   SET embedding_next = CAST(:embedding AS vector),
       embedding_next_model = :embedding_next_model,
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
(`services/memory/app/vectorstore/pgvector_store.py:95-97`). The same contract applies to the next-generation statement:
`expected_revision` still guards it, and a `rowcount != 1` must still raise. Every predicate that makes the current write
safe is load-bearing here too — `org_id` for tenancy, `deleted_at` / `tombstoned` / `status` so a forget or delete
between the read and the write is refused rather than undone, and `lifecycle_revision` so a superseded row is skipped. Do
not drop one to raise the row count: a missing `org_id` is a cross-tenant write.

Per row:

1. Read `id`, `content`, and `lifecycle_revision`.
2. Embed the text (Step 3 caps). Recall Step 2: one embedder process serves one generation, so the next-generation
   vector comes from the next-generation backend, not from reinterpreting the current one.
3. Write the **next** generation with the revision that was read, through the statement sketched above. It writes
   `embedding_next` / `embedding_next_model` and nothing else; `embedding` is left to the live write path.
4. On `LookupError`, do not retry blindly: the row was superseded, tombstoned, forgotten, or deleted between the read and
   the write. Count it as skipped and let the next pass see the new revision. Writing with a stale revision would
   resurrect an embedding on a row a legal hold is trying to erase.

CAS is not optional here: the memory service's own write path uses the same fence on the same rows, so the backfill
competes with live writes.

### Step 5 — index per generation during the window

The vector index is a single partial HNSW index on `embedding`
(`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:94-98`). During the window the new generation needs its
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

### Step 6 — cut the reader over to the new generation, only after the backfill completes

**Gate:** the backfill is complete when, for every organization, the count of visible rows whose `embedding_next` is null
or whose `embedding_next_model` is not the next identity is zero. Check that count; do not infer completion from a job
log. Because Step 2 keeps filling the next column for new rows, this count covers the backfilled corpus and everything
written during the window in one number.

Only then change the reader to the new column and generation. The reason for the order is the index, not convenience: an
HNSW scan returns its top-k candidates before any predicate on a non-indexed column is applied, so a "filter by
`embedding_model`" applied after the scan shrinks the result set below `LIMIT` and loses recall for exactly the rows that
are not yet backfilled. Ordering the filter after a complete backfill means there is nothing left to drop. pgvector 0.8+
exposes iterative scan (`off` / `relaxed_order` / `strict_order`, see the comment at
`services/memory/app/vectorstore/base.py:81-84`) as the mitigation when a filtered scan is unavoidable; it buys recall
with latency and is not a substitute for the gate above. The fence is a vector-channel control: it bounds HNSW
candidates only, so the full-text channels keep returning cross-generation keyword hits until they are fenced too
(`services/memory/app/read/repository.py:206-211`).

Sequence:

1. Deploy the reader on `embedding_next` and the next identity. The writer keeps filling both generations across that
   deploy (Step 2), so no row becomes unreadable at the switch, and the current column remains a complete rollback copy.
2. Verify retrieval on a known query set before dropping anything (Step 7).
3. Only after Step 7 passes, stop maintaining the current generation in the writer, and then drop the old index and the
   old column, in a later change.

### Step 7 — verify, at the pre-drop gate and again after the drop

Two checkpoints, because the safe state differs either side of the drop.

**Pre-drop gate** — the old column still exists, is still maintained, and the reader is on `embedding_next`:

- Counts: new-generation rows = visible rows that carry a vector, and zero such rows are missing **either** generation —
  `embedding` / `embedding_model` for the current identity, `embedding_next` / `embedding_next_model` for the next. Every
  visible row with a vector is expected to carry both at this point; a nonzero "missing either generation" count is the
  failure. "Rows with both generations = 0" would be the opposite of the safe state here. A visible row with no vector at
  all is a separate defect, not a migration gap: the write path's after-commit upsert is best-effort
  (`services/memory/app/write/after_commit.py:54-60`), so count it separately or the denominator hides it.
- Retrieval: the same query set returns the same neighbours from the new generation as from the old, within the recall
  agreement the ranking gate already measures (`engineering/adr/0061-retrieval-quality-benchmark-methodology.md`). A
  generation that changes neighbours without a quality gain is a regression, not a migration. Compare the vector channel
  on its own: the fence does not cover full-text results.
- Errors: no `LookupError` storm in the backfill log (a storm means live writes are racing the pass), and no
  `embedding_dim` check violation.
- Cache: the old namespace is either purged or unreachable by the new identity.

**Post-drop cleanup** — the old column has been removed in the later change:

- Counts: zero rows still carry the old generation — no surviving identity column records the old identity — and every
  visible row that carried a vector before the drop still carries the new one. The first check is only meaningful after
  the drop, when nothing can write the old generation any more; the second catches a drop that took rows with it.
- Retrieval: re-run the same query set against the surviving column, so the drop is verified rather than assumed.

### Rollback

Rollback is a revert, not a re-embed, and that is the point of Steps 2 and 6:

1. Point the reader back at the old column. One query change and one deploy; no data is written. This only works while
   the current generation is still being maintained for rows created since the switch, which is why Step 2 keeps filling
   it until Step 7 has passed.
2. Leave the new generation in place. It is inert until a reader uses it, and dropping it destroys the only copy of work
   that may take hours to redo.
3. If the switch also moved the identity settings, revert them in the same change as the reader:
   `IBEX_EMBEDDING_MODEL` / `IBEX_EMBEDDING_MODEL_REVISION` on the embedder
   (`services/embedder/app/config.py:42-52`) and `IBEX_MEMORY_EMBEDDING_MODEL` /
   `IBEX_MEMORY_EMBEDDING_MODEL_REVISION` on the memory service (`services/memory/app/config.py:164-184`). Leave them
   forward and the write path keeps producing the new generation while every reader is back on the old one.
4. Purge the cache namespace for the abandoned identity, or a later switch back will serve vectors from the abandoned
   generation.

The one case with no clean revert is a *dimension* change, which is why it is out of scope above: the column type moves,
and going back is a second table rewrite.

## What is missing today, and what that costs

Every bullet here describes the current tree; re-verify before you rely on one.

- **No job ledger.** No table records which rows a pass has completed. A restart redoes the batch it was in and
  everything after the last checkpoint it did not persist; the work is idempotent (the CAS write puts the same
  next-generation vector in the same column for the same identity and revision) but it is not resumable, so a large
  corpus costs the full pass again after an interruption. Keyset pagination (Step 3) bounds the loss to one batch; a
  ledger would remove it. Do not invent one here.
- **No generation column, no generation-aware write, no backfill task, no per-generation index.**
  `ibex.worker.embedding.noop` is the only embedding task (`services/worker/app/task_names.py:5,18`).
  `SearchRequest` carries an optional `embedding_model` fence (`services/memory/app/vectorstore/base.py:58-108`), but it
  defaults to off, filters one HNSW candidate set, and bounds vector candidates only — the full-text channels are not
  fenced (`services/memory/app/read/repository.py:206-211`). `PgVectorStore.upsert` writes `embedding*` and never
  `embedding_next*` (`services/memory/app/vectorstore/pgvector_store.py:74-77`), and the write path embeds once per
  memory (`services/memory/app/write/factory.py:85-92`), so nothing today can produce two generations for one row.
  Steps 2, 4, 5, and 6 are designs until a generation column, a generation-aware write, a backfill task, and a
  per-generation index land.
- **Erasure does not know about a second generation.** Forget nulls `embedding`, `embedding_model`, and `embedding_dim`
  (`services/memory/app/lifecycle.py:133-135`) and `PgVectorStore.delete` does the same
  (`services/memory/app/vectorstore/pgvector_store.py:169-181`); neither names `embedding_next*`. A second generation
  added without changing both leaves a forgotten row's vector readable in the new column. Fix it in the same change that
  adds the column, and cover it with a test that forgets a row carrying both generations.
- **Provenance is a claim, not a measurement.** The row records the configured identity — `IBEX_MEMORY_EMBEDDING_MODEL`,
  or `id@revision` when `IBEX_MEMORY_EMBEDDING_MODEL_REVISION` is set (`services/memory/app/config.py:164-184,428-465`)
  — not the embedder's reported `model_id` (`services/memory/app/write/factory.py:85-92`), so a mis-set id labels every
  generation identically and the cut-over cannot be verified from the model column alone. Verify by sampling vectors
  against the pinned backend.
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
