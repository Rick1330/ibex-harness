# Ranking-quality gold set (v1)

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
