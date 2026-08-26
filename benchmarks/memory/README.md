# Memory HNSW benches (Phase 3 / m3.2.1)

Lives under the top-level [`benchmarks/`](../README.md) tree so recall/latency
results share the same publish surface as proxy benches (`web/public/benchmarks/`)
and the [benchmark bot](https://github.com/Rick1330/ibexharness-benchmark-bot).

The runner imports `services/memory` (`PgVectorStore`) via `PYTHONPATH` — the
service owns the VectorStore implementation; this directory owns measurement +
published history.

## What it measures

Synthetic semi-dense unit-vector corpus against live `pgvector` HNSW
(`idx_memories_embedding_hnsw`, default `ef_search=40`):

- **recall@10** — planted near-neighbor must appear in top-10
- **latency** — wall-clock `PgVectorStore.search` p50/p95/p99 (+ bootstrap 95% CI on p95)
- **plan gate** — `EXPLAIN (ANALYZE, BUFFERS)` must use `idx_memories_embedding_hnsw`
- **pg_stat gate** — `idx_scan` on that index must increase across the timed batch

### Hard methodology rules

1. `TRUNCATE ibex_core.memories CASCADE` at script start and before every size
2. Assert `count(*) == corpus_size` before timing
3. `ANALYZE ibex_core.memories` after COPY
4. ≥100 discarded warm-up queries (optional `pg_prewarm` when available)
5. Default `--ef-search 40` (roadmap SLA); overrides must be explicit CLI flags
6. Seed **once** per `(corpus_size × index_build_mode)`; search knobs
   (`min_similarity` × `iterative_scan`) reuse that corpus (no 4× re-seed)

## Profiles / published knobs

CI (`memory-benchmark.yml`) always measures with production publish knobs:

```bash
--ef-search 40 --min-similarity 0.70 --iterative-scan off --index-build-mode bulk
```

`build_published_data.py` filters to those cells and attaches `status` /
`gate_summary` (recall ≥ 98%; 1M p95/p99 SLAs when a 1M cell exists — otherwise
`warn` on smoke/fast). Full local matrices (`0.0 0.70`, iterative modes, incremental)
remain useful for investigation but are **not** published.

## Run

From repo root (compose-test Postgres on `:5433`):

```bash
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench-smoke          # 10K only

# Match CI published knobs (10K + 100K; avoid 1M on a laptop):
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  MEMORY_BENCH_SIZES='10000 100000' \
  bash infra/scripts/memory-bench.sh \
    --ef-search 40 \
    --min-similarity 0.70 \
    --iterative-scan off \
    --index-build-mode bulk
```

Useful flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--ef-search` | `40` | `hnsw.ef_search` |
| `--min-similarity` | `0.0 0.70` | production default is `0.70` |
| `--iterative-scan` | `off relaxed_order` | pgvector 0.8 filtered-ANN continuation |
| `--index-build-mode` | `incremental` | `bulk` = COPY then `CREATE INDEX` |
| `--queries` | size defaults | override timed query count |

Artifacts:

| Path | Role |
| --- | --- |
| `benchmarks/memory/output/hnsw_recall_latency.json` | Latest raw run |
| `web/public/benchmarks/hnsw-benchmark-data.json` | Published history (site + bot) |

Schema: [`../data-schema/hnsw-benchmark-data.schema.json`](../data-schema/hnsw-benchmark-data.schema.json).
Methodology: [ADR-0053](/docs/adr/0053-vector-store-abstraction).

**1M corpora belong on CI**, not a developer laptop.
