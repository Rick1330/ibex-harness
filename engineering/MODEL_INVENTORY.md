# Model Inventory

**Status:** `provisional`. Every model the platform can run is recorded here, with the place the code enforces its
identity where one exists. No licence and almost no revision is recorded anywhere in the repository, and no re-embedding
path exists. Ledger row: [`architecture-v2/00-status-and-evidence.md`](architecture-v2/00-status-and-evidence.md) §
Current baseline.

**Scope:** three runtime roles — the extraction LLM (`services/worker`), the embedding model
(`services/embedder` → `ibex_core.memories.embedding`), and the reranker (`services/memory` read path, default off).
Fifteen rows in total: 2 extraction, 10 embedding, 3 reranker.
Proxy provider routing is out of scope here: its per-model data is `infra/provider-capabilities/manifest.v1.json`,
which records context window and tokenizer family but no licence, no revision, and no embedding row.

**Verified at:** base commit `3c7532cd`, with this branch's embedding-identity changes applied to §2 and
*Known misconfigurations* (configurable model id, the search fence, the revision in the cache digest). Every claim below
describes the tree you are reading; re-verify a row against its cited file before relying on it. The *Known
misconfigurations* section is the part most likely to go stale: if a later change fixes one, re-verify and update this
file and the JSON twin in the same commit.

## How to read this file

- **Traceability.** Every id, dimension, and pin cites the file and line that states it. Nothing is inferred from a
  model's public documentation, and no external registry was consulted to fill a cell.
- **`not recorded`.** The repository states nothing for that cell. It is a finding, not a euphemism: it is why the
  status is `provisional`.
- **Machine-readable twin.** `infra/model-inventory.v1.json` carries the same rows for tooling and uses `null` where
  this file says `not recorded`. Change both in one commit.
- **Column meanings.** *Revision* is the weight or serving revision the deployment is tied to, not the version of a
  client library. *Fallback* is what the code does when the model cannot be used — not a preference order. *Pin status*
  is whether a tag, digest, or revision would move under you on a redeploy.

## 1) Extraction LLM (worker)

`IBEX_WORKER_EXTRACTION_PROVIDER` selects one profile, once, at startup (`services/worker/app/extraction/factory.py:18-31`).
There is no provider chain in the worker: an unusable provider is an error, not a downgrade.

| Model id | Revision | Dimensions | Licence | Fallback | Configuration env var | Pin status |
|---|---|---|---|---|---|---|
| `gpt-4o-mini` (profile `openai`) | not recorded | not applicable (chat) | not recorded | None. An unknown profile raises, and profile `openai` raises without `OPENAI_API_KEY` (`services/worker/app/extraction/factory.py:18-45`). | `IBEX_WORKER_EXTRACTION_OPENAI_MODEL`, alias `EXTRACTION_OPENAI_MODEL` (`services/worker/app/config.py:181-188`); default at `services/worker/app/extraction/openai_provider.py:11` | Floating alias. The id resolves to whatever the provider currently serves; no dated snapshot is recorded. |
| `Qwen2.5-14B-Instruct` (profile `vllm`) | not recorded | not applicable (chat) | not recorded | None. Profile `vllm` raises without a base URL (`services/worker/app/extraction/factory.py:47-60`). | `IBEX_WORKER_EXTRACTION_VLLM_MODEL`, alias `EXTRACTION_VLLM_MODEL` (`services/worker/app/config.py:205-212`); default at `services/worker/app/extraction/vllm_provider.py:10` | Floating label. The id must match the vLLM server's served-model name; no weights revision is recorded in this repository. |

## 2) Embedding

`IBEX_EMBEDDING_PROFILE` (`cpu` | `gpu` | `hosted`) picks the backend, and `IBEX_EMBEDDING_MODEL` /
`IBEX_EMBEDDING_DIM` override the profile defaults (`services/embedder/app/config.py:155-166`). The resolved pair is the
identity the service reports. The memory write path records a separate setting, `IBEX_MEMORY_EMBEDDING_MODEL`
(`services/memory/app/config.py:160-180`), which is the operator's claim about that identity rather than a value read
back from it.

The identity is enforced at startup, not merely declared: the `gpu` backend compares the TEI `/info` `model_id` and the
reported dimensions against the configured pair and refuses readiness on either mismatch
(`services/embedder/app/main.py:97-113`). A revision is not part of that comparison — TEI reports the model id, so two
revisions of the same id are indistinguishable to the check.

The column is fixed-width: `memories.embedding` is `vector(1024)` and the check constraint requires
`embedding_dim = 1024`, with `embedding_model` capped at 256 characters
(`infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:13-16,36-45`). Only a 1024-dimension model can be
stored today; the 384- and 3072-dimension rows below are configured but not writable without a schema change.
Organizations carry their own `embedding_profile`, `embedding_dim`, and `embedding_model_id`, defaulting to
`cpu`, `384`, and `all-MiniLM-L6-v2` (`infra/migrations/postgres/000013_organizations_embedding_profile.up.sql:1-7`).

| Profile | Model id | Revision | Dimensions | Licence | Fallback | Configuration env var | Pin status |
|---|---|---|---|---|---|---|---|
| `cpu` | `all-MiniLM-L6-v2` | not recorded | 384 (`services/embedder/app/profiles.py:28`) | not recorded | None. `cpu` returns the deterministic stub (`services/embedder/app/factory.py:54-61`), so no model is served and this id is a geometry label. | `IBEX_EMBEDDING_PROFILE=cpu`, optionally `IBEX_EMBEDDING_MODEL` / `IBEX_EMBEDDING_DIM` (`services/embedder/app/config.py:35-37`) | Label only; nothing is pinned because nothing is loaded. The shipped dev bundle overrides the dimension to 1024 — see *Known misconfigurations*. |
| `gpu` | `BAAI/bge-m3` | `5617a9f61b028005a4858fdac845db406aefb181`, recorded in the deployment only (`infra/compose/v1-single-node/compose.yml:362`) | 1024 (`services/embedder/app/profiles.py:30`) | not recorded | None. `gpu` without `IBEX_EMBEDDING_TEI_BASE_URL` raises, and a `gpu`→stub fallback is explicitly prohibited as a geometry lie (`services/embedder/app/factory.py:13-14,92-97`). | `IBEX_EMBEDDING_TEI_BASE_URL`, `IBEX_EMBEDDING_MODEL`, `IBEX_EMBEDDING_DIM` (`infra/compose/v1-single-node/compose.yml:335-338`) | Pinned in `v1-single-node`: image digest `cpu-1.9.4@sha256:2538ea1c…` and the weights revision above (`infra/compose/v1-single-node/compose.yml:358,361-362`). Unpinned in `infra/reference/tei-embeddings.compose.yaml:47` (floating `cpu-1.6`, no `--revision`). The embedder records no revision: its TEI request carries only `inputs` (`services/embedder/app/tei/client.py:170-175`), and the served model is whatever the server was started with. |
| `hosted` / `openai` | `text-embedding-3-large` | not recorded | 3072 default, Matryoshka 1..3072 (`services/embedder/app/hosted/providers.py:34-37`) | not recorded | Provider default when `IBEX_EMBEDDING_MODEL` is unset (`services/embedder/app/hosted/providers.py:67-72`). No cross-provider fallback exists: `voyage` fails closed (`services/embedder/app/hosted/providers.py:79-82`). | `IBEX_EMBEDDING_HOSTED_PROVIDER=openai`, `IBEX_EMBEDDING_MODEL`, `IBEX_EMBEDDING_DIM`, `IBEX_EMBEDDING_HOSTED_API_KEY` (`services/embedder/app/hosted/env.py:35-50`) | Unpinned by construction. The API takes a model id and offers no snapshot or revision parameter, so no revision can be recorded. |
| `hosted` / `openai` | `text-embedding-3-small` | not recorded | 1536 maximum, Matryoshka (`services/embedder/app/hosted/providers.py:36`) | not recorded | Catalogued only; not a profile default. | `IBEX_EMBEDDING_MODEL=text-embedding-3-small`, `IBEX_EMBEDDING_DIM` | Unpinned by construction, as above. |
| `hosted` / `openai` | `text-embedding-ada-002` | not recorded | 1536 fixed, no `dimensions` parameter (`services/embedder/app/hosted/providers.py:6-8,125-134`) | not recorded | Catalogued only; a dimension other than 1536 raises (`services/embedder/app/hosted/providers.py:131-134`). | `IBEX_EMBEDDING_MODEL=text-embedding-ada-002`, `IBEX_EMBEDDING_DIM=1536` | Unpinned by construction, as above. |
| `hosted` / `cohere` | `embed-english-v3.0` | not recorded | 1024 fixed (`services/embedder/app/hosted/providers.py:41`) | not recorded | Cohere provider default (`services/embedder/app/hosted/providers.py:73-78`). | `IBEX_EMBEDDING_HOSTED_PROVIDER=cohere`, `IBEX_EMBEDDING_MODEL`, `IBEX_EMBEDDING_DIM` | Unpinned by construction: the v3.0 family takes no output dimension and no revision. |
| `hosted` / `cohere` | `embed-multilingual-v3.0` | not recorded | 1024 fixed (`services/embedder/app/hosted/providers.py:42`) | not recorded | Catalogued only; a mismatched dimension raises (`services/embedder/app/hosted/providers.py:137-142`). | `IBEX_EMBEDDING_MODEL=embed-multilingual-v3.0`, `IBEX_EMBEDDING_DIM=1024` | Unpinned by construction, as above. |
| `hosted` / `cohere` | `embed-english-light-v3.0` | not recorded | 384 fixed (`services/embedder/app/hosted/providers.py:43`) | not recorded | Catalogued only. Not storable: the column requires 1024 dimensions. | `IBEX_EMBEDDING_MODEL=embed-english-light-v3.0`, `IBEX_EMBEDDING_DIM=384` | Unpinned by construction, as above. |
| `hosted` / `cohere` | `embed-multilingual-light-v3.0` | not recorded | 384 fixed (`services/embedder/app/hosted/providers.py:44`) | not recorded | Catalogued only. Not storable, as above. | `IBEX_EMBEDDING_MODEL=embed-multilingual-light-v3.0`, `IBEX_EMBEDDING_DIM=384` | Unpinned by construction, as above. |
| `hosted` / `voyage` | none — no model is recorded | not recorded | not recorded | not recorded | Fails closed: `provider_defaults` raises `BackendUnavailableError` for `voyage` (`services/embedder/app/hosted/providers.py:79-82`). | `IBEX_EMBEDDING_HOSTED_PROVIDER=voyage` is accepted by the validator (`services/embedder/app/hosted/providers.py:55-63`) and then refused at construction | Not applicable: no client exists. |

## 3) Reranker (memory read path, default off)

| Model id | Revision | Dimensions | Licence | Fallback | Configuration env var | Pin status |
|---|---|---|---|---|---|---|
| not recorded — no model is named anywhere | not recorded | not applicable | not recorded | Degrade to the fused order. Reranking is default-off, and every failure returns the fusion order rather than an error (`services/memory/app/clients/rerank.py:1-14`). | `IBEX_MEMORY_RERANK_ENABLED` (default off), `IBEX_MEMORY_RERANK_BASE_URL` (default `http://127.0.0.1:8006`), `IBEX_MEMORY_RERANK_API_TOKEN` with alias `IBEX_RERANK_API_TOKEN` (`services/memory/app/config.py:247-263`) | Unpinned and unnamed. The client posts to TEI `POST /rerank`, so the model is whatever the server was started with; no Compose service, Helm value, or `--model-id` for a reranker exists in this repository. |
| `BAAI/bge-reranker-v2-m3` | not recorded | not applicable | not recorded | Not deployed; nothing resolves this id. | None — no environment variable names it. | Cited only. It appears in the references of ADR-0093 (`engineering/adr/0093-cross-encoder-rerank-as-relevance.md:102`), a record that is still `Proposed` and deploys no model. |
| `stub/lexical-overlap@1` | not applicable (deterministic scorer) | not applicable | not recorded | Not a model; there is nothing to fall back from. | None; it is selected inside the benchmark driver, not the service. | A deliberately self-naming stand-in (`benchmarks/memory/ranking_quality/rerank_stub.py:1-22`). Every artifact it contributes to carries this label in place of a model name. |

## Fields an owner must fill

**Licence for all fifteen rows, revision for fourteen of them, and the reranker's identity, need an owner: nothing in
this repository records any of them.** The readiness audit records the same gap as P1-31 ("No model provenance inventory
(model, revision, licence, fallback); extraction defaults are floating aliases") and P1-33 ("The reranker is
unnamed/unpinned and no artifact provides it") in `engineering/architecture-v2/27-v1-readiness-audit.md:121-123`.

| Field | Rows with no recorded value | What filling it requires |
|---|---|---|
| Licence | 15 of 15 | The upstream licence text for each model, recorded here and in the JSON twin. Three different licences are plausible across these families; none is asserted. |
| Revision (weights) | 14 of 15 — `BAAI/bge-m3` is the exception, and only in `v1-single-node` | A commit hash or snapshot id per model, and the place that enforces it (Compose `--revision`, a provider snapshot parameter, or a served-model hash). |
| Reranker identity | 1 of 1 deployed row | The `--model-id` the reranker is started with, plus a Compose or Helm entry that starts it. |

## Known misconfigurations

### The dev bundle labels a 384-dimension model at 1024 dimensions

`infra/compose/bundles/memory-context.yml:70-71` sets `IBEX_EMBEDDING_PROFILE: cpu` together with
`IBEX_EMBEDDING_DIM: "1024"`. Profile `cpu` resolves to `StubBackend` (`services/embedder/app/factory.py:54-61`), whose
`model_id` is `all-MiniLM-L6-v2` — a 384-dimension id (`services/embedder/app/profiles.py:28`) — while `DIM` overrides
the profile dimension (`services/embedder/app/config.py:164-166`). Writes therefore satisfy the `embedding_dim = 1024`
check at `infra/migrations/postgres/000017_memory_schema_v2_expand.up.sql:36` while the recorded model name describes a
model that never runs. `infra/bundles/memory-context.json:16` already declares the stub geometry; the dimension override
is the part that contradicts it.

The shipped `v1-single-node` profile does not share the defect: it sets `gpu`, `1024`, and `BAAI/bge-m3` together
(`infra/compose/v1-single-node/compose.yml:335-337`).

### `memories.embedding_model` records a configuration value, not the producing model

The write path records `Settings.embedding_model`, resolved through `resolve_embedding_model`
(`services/memory/app/config.py:160-180,426-436`), and the after-commit handler defaults to the same resolver
(`services/memory/app/write/after_commit.py:23-26,50`). The default is `bge-m3`
(`services/memory/app/config.py:163-165`), so the id is no longer a hardcoded literal: it is configurable through
`IBEX_MEMORY_EMBEDDING_MODEL` (`services/memory/app/write/orchestrator.py:76,262-273`). The embedder's response does
carry a `model_id` (`services/memory/app/clients/embedding.py:79,276-281`), but `build_embedding_callable` returns only
`result.vectors[0]` and drops it (`services/memory/app/write/factory.py:85-92`). The stored value is therefore the
operator's configured claim, not the model the embedder reported: an operator who sets the variable to the wrong id
stamps every row with it, and nothing compares the two. This is the first thing the re-embed runbook has to fix: the
provenance column records a claim, not a measured generation.

### Search fences by model, but the fence is off by default

`SEARCH_SQL` accepts an optional `embedding_model` predicate alongside the organization, agent, status, lifecycle, and
validity filters (`services/memory/app/vectorstore/pgvector_store.py:16-50`). The predicate is inert when the bind value
is NULL, and `SearchMemoriesRequest.embedding_model` defaults to `None`
(`services/memory/app/schemas/search.py:19-48`), so a default request still compares every generation in the column.
Two residual gaps remain. First, the fence bounds only the vector channel: the full-text channels match tokens and score
by `ts_rank_cd`, never by cosine, so they can still surface a row recorded under another generation
(`services/memory/app/read/repository.py:198-211`). Second, a fenced search is a post-filter over the HNSW candidate
set: the scan yields candidates and the predicate removes the other generations afterwards, so a window that is mostly
other generations returns fewer rows and loses recall; a per-generation partial index is the migration path, not a wider
`LIMIT` (`services/memory/app/vectorstore/pgvector_store.py:98-119`).

### The cache key covers the revision only when one is configured

`content_digest` hashes `(model_id, dimensions, [revision], text)` through `EmbeddingIdentity`
(`services/embedder/app/cache/keys.py:13-55`), and the cache resolves the backend's `model_id`, `dimensions` and
`model_revision` into that identity once (`services/embedder/app/cache/backend.py:97-105`). The revision is hashed only
when it is non-empty, so a deployment that never sets `IBEX_EMBEDDING_MODEL_REVISION` keeps the pre-revision byte layout
and every vector already in Redis. The residual gap is the pairing: pinning `--revision` in Compose does not set
`IBEX_EMBEDDING_MODEL_REVISION`, and nothing compares the two, so an operator can move the weights and still share
cached vectors for the TTL. Configure the variable whenever the revision is pinned; configuring it invalidates existing
entries, which then recompute from the new weights rather than being served as if they came from them.

### There is no re-embed path

`ibex.worker.embedding.noop` is the only embedding task registered (`services/worker/app/task_names.py:5,18`). No
backfill task and no generation column exist, and search has no per-generation index: the optional model fence filters
one HNSW candidate set rather than routing to a generation's own index
(`services/memory/app/vectorstore/pgvector_store.py:98-119`). `engineering/runbooks/re-embed.md` is the procedure that
has to be built before a model can be changed in place.

## A record that is stale, not a claim to repeat

The readiness audit says TEI has no pinned image or model "in any profile" and "anywhere"
(`engineering/architecture-v2/27-v1-readiness-audit.md:93,96`, rows P1-04 and P1-05). Since commit `89acc096`,
`infra/compose/v1-single-node/compose.yml:358,361-362` pins both the image digest and the weights revision. The audit's
sentence remains true of `infra/reference/tei-embeddings.compose.yaml:47` only. The stale row is the audit's, not the
Compose file's; this inventory follows the file.

## Related

- `infra/model-inventory.v1.json` — the machine-readable twin of these tables.
- `engineering/runbooks/re-embed.md` — the re-embedding procedure, and what it still requires.
- `infra/provider-capabilities/manifest.v1.json` — proxy-side model capabilities (context window, tokenizer family).
- `engineering/ENVIRONMENT_VARIABLES.md` — `IBEX_EMBEDDING_*` and `IBEX_WORKER_EXTRACTION_*` variable reference.
- ADR-0046 (`engineering/adr/0046-embedder-interface-registry.md`) — profiles and why dimensions are not interchangeable.
- ADR-0097 (`engineering/adr/0097-v1-supported-profile.md`) — `v1-single-node` and its pinned TEI/bge-m3 backend.
