# Benchmarks

This directory contains:

1. **Proxy / load benchmark pipeline** (Phases 0–2) — Go stage microbenches, k6, published
   `web/public/benchmarks/benchmark-data.json` → site `/benchmarks`.
2. **Memory HNSW recall/latency benches** (Phase 3 Track B) — `memory/` exercising
   `services/memory` `PgVectorStore` against live pgvector; published
   `web/public/benchmarks/hnsw-benchmark-data.json` → site `/benchmarks/memory`.

Methodology: [ADR-0034](/docs/adr/0034-performance-methodology) (proxy),
[ADR-0053](/docs/adr/0053-vector-store-abstraction) (vector store). Roadmap:
[current state](https://ibexharness.com/roadmap/current-state).

---

## What exists today

### Proxy

- `go/`: warm-path proxy overhead stage microbenchmarks (authcache, ratelimit, directive, injection).
- `services/proxy/internal/http`: `/health` (`BenchmarkProxyHealth`) and full chat overhead (`BenchmarkProxyChatOverhead`) with mockllm.
- `k6/`: load test script — `/health` for smoke/fast; chat path when `K6_USE_CHAT=1`.
- `scripts/`: aggregation, regression gate, published data builders, and proxy stack helpers.
- `data-schema/`: baseline policy, JSON schema, and benchmark data contracts (proxy + HNSW).
- `testdata/`: fixtures for pipeline verification tests.

Published proxy data is committed via the benchmark bot after successful **main** collects
(`benchmark_main_complete` → artifact `benchmark-data`).

### Suite contract (multi-bench)

Each suite keeps its own JSON file and bot modules. Shared seams:

| Field | Proxy | Memory HNSW | Future suite |
| --- | --- | --- | --- |
| `suite_id` | `proxy` | `hnsw` | e.g. `extraction` |
| Artifact | `benchmark-data` | `hnsw-benchmark-data` | `<suite>-benchmark-data` |
| Public path | `web/public/benchmarks/benchmark-data.json` | `…/hnsw-benchmark-data.json` | under same dir |
| Dispatch | `benchmark_main_complete` | `memory_benchmark_main_complete` | new event type |
| PR comment marker | `IBEX_BOT_COMMENT` | `IBEX_BOT_COMMENT_HNSW` | new marker |
| Bot pin helper | `.github/actions/setup-benchmark-bot` | same | same |
| Site registry | `web/src/lib/benchmarks/suites.ts` | same | add suite + nav pages |

Do **not** merge suites into one mega-JSON. Site nav groups by suite; proxy-only concepts
(waterfall / k6 load) are not invented for HNSW.

### Memory HNSW

- `memory/hnsw_bench.py`: CLI + published payload builder.
- `memory/hnsw_run.py`: corpus seed + search-matrix measurement helpers.
- `memory/publish_cells.py`: production cell filter + `status` / `gate_summary` helpers.
- `memory/build_published_data.py`: merge raw JSON into `hnsw-benchmark-data.json` (uses
  `publish_cells`).
- `scripts/validate_published_hnsw.py`: CI contract checks for published HNSW history.
- `data-schema/hnsw-benchmark-data.schema.json`: Zod/CI contract for the HNSW file.
- Workflow: `.github/workflows/memory-benchmark.yml` (name **`Memory Benchmarks`**).
- Bot setup: `.github/actions/setup-benchmark-bot` (pin + optional `BENCHMARK_BOT_RELEASE_TAG`;
  Memory collect requires subcommand `post-hnsw-pr-comment`).
- Bot dispatch: `memory_benchmark_main_complete` → artifact `hnsw-benchmark-data` only
  (does **not** touch proxy `benchmark-data.json` / `badge.svg`).
- Same-repo PRs also get a **Memory HNSW** sticky PR comment (`post-hnsw-pr-comment`)
  separate from the proxy comment (suite badge, corpus table, gate summary, site links).
- Published cells are production knobs only: `ef_search=40`, `min_similarity=0.70`,
  `iterative_scan=off`, `index_build_mode=bulk` (full matrix stays in raw output).
- Site suite: `/benchmarks/memory` (+ latency / history / compare).

```bash
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench-smoke
POSTGRES_TEST_DSN=postgres://ibex:ibex@localhost:5433/ibex_test?sslmode=disable \
  make memory-bench
```

## Profiles (proxy — speed vs quality)

| Profile | When | Go `-count` | k6 | Path | Proxy HTTP bench |
| --- | --- | --- | --- | --- | --- |
| `smoke` | Pull requests | 1 | 15 VUs / 15s | `GET /health` | skipped |
| `fast` | Daily cron (Mon–Sat), main pushes | 2 | 25 VUs / 30s | `GET /health` | yes |
| `full` | Sunday cron, `workflow_dispatch` | 5 | 100 VUs / 2m | `POST /v1/chat/completions` (`K6_USE_CHAT=1`) | yes |

Target wall-clock: **~2–4 min** for `smoke` PRs, **~5–10 min** for `fast`, current quality bar for `full`. All keep Postgres + Redis + real proxy. Go stage microbenches run before stack start. Each published run records `profile: "smoke" | "fast" | "full"`.

Stack helper seeds the DB and exports `IBEX_DEV_TOKEN` / `IBEX_DEV_AGENT_ID`; `IBEX_LLM_MODE=mock` registers an immediate stub provider so chat returns **200**.

### Memory sizes (Memory Benchmarks workflow)

| Trigger | Corpus sizes |
| --- | --- |
| `pull_request` | 10K (smoke) |
| `push` to `main` | 10K + 100K |
| `schedule` (Sunday) / `workflow_dispatch` | 10K + 100K + 1M |

## Planned expansions (do not invent paths early)

| Concern | Preferred phase | Likely home (orientation) |
| --- | --- | --- |
| Extraction quality gold-set / regression gate | **3.5** | Under `services/worker/eval/` |
| Context-assembly latency under degradation ladder | **3.5** | Proxy + context integration suites |
| Multi-provider resilience / breaker benches | **4** | Proxy + k6 scenarios |
| Drift / regression-suite CI gates | **4.5** | Worker + API |
| Hybrid retrieval / shadow eval | **5** | Memory/context + optional production shadow sampler |

When those land, update this README, ADR-0034 (or a follow-on ADR), and the public `/benchmarks` docs in the same change set.

## Verification

```bash
go test ./benchmarks/go/...
python benchmarks/scripts/test_pipeline.py
cd web && npm test -- src/lib/benchmarks/ && npm run typecheck
```

## Local quick run (proxy)

```bash
go test ./benchmarks/go -run=^$ -bench=. -benchmem -count=2 > benchmarks/output/go-bench.txt
go test ./services/proxy/internal/http -run=^$ -bench=BenchmarkProxy -benchmem -count=2 >> benchmarks/output/go-bench.txt
```

Load benchmarks require a running proxy stack:

```bash
bash benchmarks/scripts/start_proxy_stack.sh
docker run --rm --network host -v "$PWD:/work" -w /work \
  -e BASE_URL=http://127.0.0.1:18082 -e K6_HEALTH_PATH=/health \
  -e K6_USE_CHAT=1 \
  -e IBEX_DEV_TOKEN=ibex_pat_00000000-0000-0000-0000-000000000004_LOCALDEVELOPMENTONLY \
  -e IBEX_DEV_AGENT_ID=00000000-0000-0000-0000-000000000003 \
  -e K6_VUS=25 -e K6_DURATION=30s \
  grafana/k6:0.53.0 run benchmarks/k6/proxy_load.js \
  --summary-trend-stats="med,p(90),p(95),p(99),p(99.9),min,max" \
  --summary-export benchmarks/output/k6-summary.json
bash benchmarks/scripts/stop_proxy_stack.sh
BENCH_PROFILE=fast python benchmarks/scripts/aggregate_metrics.py
python benchmarks/scripts/regression_gate.py
BENCH_PROFILE=fast python benchmarks/scripts/build_benchmark_data.py
python benchmarks/scripts/generate_badge.py
```
