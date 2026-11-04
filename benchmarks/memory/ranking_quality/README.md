# Ranking-quality gold sets (v1 and v2)

The directory holds two corpora with different purposes. **v1** is the composite-ranking
regression gate that CI has run since milestone 3.D.1; **v2** is the Phase 5 corpus the
retrieval-mode comparison is measured on. They share the seeding code and the org namespace, and
a run seeds one at a time — `seed_gold_set` purges the org before inserting.

| | v1 | v2 |
|---|---|---|
| File | `gold_set_v1.json` | `gold_set_v2.json` |
| Size | 50 memories, 20 queries | 150 queries over 60 / 50 / 40 dense / lexical / graph |
| Embeddings | one-hot hotspot via `zero_embedding` | weighted profile over named topics (`profiles.py`) |
| Similarity | 1.0 or 0.0, nothing in between | designed: 1.0 / 0.8 / 0.6 / 0.0, asserted by the validator |
| Configurations | one (`find_similar` with fallback off) | four named modes (`modes.py`) |
| Gate | `regression_gate.py`, percent tolerance | `check_mode_gate.py`, absolute points |
| Claim | regression gate for composite ranking | retrieval-mode comparison, CI stub reranker |

## v1 disclaimer

**v1 disclaimer:** single-labeler, small-N benchmark (50 memories, 20 queries) for a
consistent **senior backend engineer** persona on the memory platform team. This is a
regression gate for composite ranking on the read path — not a Phase 5 two-labeler
inter-rater gold set with Cohen's kappa.

## Design principles

- **Deterministic embeddings:** `zero_embedding(hotspot=…)` — same hotspot ⇒ cosine 1.0;
  orthogonal hotspots excluded at `min_similarity=0.5`.
- **Composite-ground-truth labels:** `expected_content_keys` match production
  `composite_score()` order (validated by `validate_gold_set.py` on every run).
- **Category coverage:** all five categories (factual, procedural, preference,
  behavioral, episodic) with ≥3 memories each.
- **Decay regression cases** (distinct from 3.D.2's 90d factual / 14d episodic dark-mode pair):
  - `q_pref_theme_decay` — 100d factual vs 14d episodic on IDE theme
  - `q_workflow_deploy_decay` — 60d procedural vs 21d behavioral on deploy workflow
  - `q_confidence_tie_break` — same-age preference pair; confidence 0.95 vs 0.70

## Contents

- `gold_set_v1.json` — labeled memories and queries (`content_key` identifiers)
- `seed.py` — loads the gold set into Postgres (dedicated org namespace)
- `bench_ranking_quality.py` — runs `MemoryReadRepository.find_similar` per query
- `regression_gate.py` — compares `output/latest.json` to committed `baseline.json`
- `metrics.py` — precision@k, recall@k, MRR (unit-tested)

### v2 corpus and the mode comparison

- `gold_set_v2.json` — the generated corpus; `generate_gold_set_v2.py` reproduces it, and
  `validate_gold_set_v2.py` asserts the structure *and* the geometry the subsets rely on
- `profiles.py` — the controlled embedding geometry (topic bases, unit-norm profiles, cosine)
- `modes.py` — the four configurations: `dense_only`, `hybrid`, `hybrid_rerank`, `full_graph`
- `run_modes.py` — the live driver: seeds v2, runs every mode over the same queries, records
  what each one returned
- `recorded_run.py`, `comparability.py` — the recording format and every rule that decides
  whether a run can be published at all
- `bench_ranking_modes.py` — scores a recording (nDCG@10 overall, non-graph, graph)
- `gate_modes.py`, `check_mode_gate.py` — the point-based gate, and its CLI
- `baseline-modes.json` — the committed scores the gate compares against
- `rerank_stub.py` — `stub/lexical-overlap@1`, the reranker CI uses

### Which reranker produced a number

`run_modes.py` can only run the stub, and refuses any other label. That is deliberate: the
cross-encoder is a network service, and the rerank stage degrades to the fused order on any
failure. A run that claims a model it never called would publish fusion's numbers under the
model's name, so the stub counts its calls and a reranked mode that never reached it is refused.

Every artifact names what produced it (`reranker`, `gold_set`), and the gate refuses to compare a
run against a baseline recorded with something else — a different experiment is not a threshold.

### What the baseline does and does not say

`baseline-modes.json` is pinned from a real run on gold set v2, and its `notes` record the
caveat that matters: `full_graph` currently scores exactly the same as `hybrid_rerank`.
Suppression does run — the twin is removed from the page — but the twin never ranks above the
expected memory for any graph query, so removing it changes no nDCG. The corpus cannot yet
distinguish the two modes, and the gate report says so with `graph_mode_distinguished: false`.
Do not read those two equal rows as evidence that graph-aware retrieval beats reranking.

### Exit codes

`check_mode_gate.py` separates three outcomes, because "we did not measure this" is not "the
measurement moved":

| code | meaning | report |
|---|---|---|
| 0 | the run is at or above its baseline | `output/modes-gate.json`, `status: pass` |
| 1 | a measured regression, or a run from another gold set or reranker | report written, with the mode table |
| 2 | an input that could not be read at all | report written, `check: input` |

Embeddings use deterministic `zero_embedding(hotspot=…)` so vector similarity is
stable without a live embedder. Category-decay cases use distinct topics/ages from
the 3.D.2 90d factual / 14d episodic dark-mode pair.

**Relevance-gate probe (m3.5.C.3):** gold set includes `gold.noise.relevance_gate_bait`
(orthogonal hotspot, high confidence/usefulness/`retrieval_count`). Default queries keep
`min_similarity=0.5` (floors ≤0.30 never filter those hits). After the query loop,
`bench_ranking_quality.py` opens retrieval (`min_similarity=0.0`, `limit=50`) and fails
unless the bait is excluded while a same-hotspot relevant memory remains.

## Run locally

From repo root (migrated Postgres on `POSTGRES_TEST_DSN`):

```bash
export POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable
export IBEX_MEMORY_DATABASE_URL="$POSTGRES_TEST_DSN"
bash infra/scripts/db-migrate.sh up
PYTHONPATH=services/memory python benchmarks/memory/ranking_quality/bench_ranking_quality.py
PYTHONPATH=services/memory python benchmarks/memory/ranking_quality/regression_gate.py
```

The mode comparison, against the v2 corpus:

```bash
# Records output/modes-recorded.json, then scores it into output/modes-latest.json.
PYTHONPATH=services/memory python benchmarks/memory/ranking_quality/run_modes.py

# Gates the scored run against baseline-modes.json; exit 1 on a regression, 2 on bad input.
PYTHONPATH=services/memory python benchmarks/memory/ranking_quality/check_mode_gate.py
```

Both steps also run in `collect-ranking-quality` in
`.github/workflows/memory-benchmark.yml`, which uploads the recording, the scored artifact and the
gate verdict. The harness tests (`pytest benchmarks/memory/ranking_quality`) need no database.
