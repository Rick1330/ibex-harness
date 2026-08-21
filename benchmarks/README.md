# Benchmarks

This directory contains the **proxy / load benchmark pipeline** used today (Phases 0–2 complete).
Retrieval-quality and intelligence eval harnesses land later under services (and possibly here) as
Phases **3.5**, **4.5**, and **5** advance — those are planning baselines, not present yet in this tree.

Methodology: [ADR-0034](/docs/adr/0034-performance-methodology). Public charts: `/benchmarks` on the site.
Roadmap alignment: [current state](https://ibexharness.com/roadmap/current-state).

---

## What exists today

- `go/`: warm-path proxy overhead stage microbenchmarks (authcache, ratelimit, directive, injection).
- `services/proxy/internal/http`: `/health` (`BenchmarkProxyHealth`) and full chat overhead (`BenchmarkProxyChatOverhead`) with mockllm.
- `k6/`: load test script — `/health` for smoke/fast; chat path when `K6_USE_CHAT=1`.
- `scripts/`: aggregation, regression gate, published data builders, and proxy stack helpers.
- `data-schema/`: baseline policy, JSON schema, and benchmark data contracts.
- `testdata/`: fixtures for pipeline verification tests.

Published benchmark data is committed to `web/public/benchmarks/` via the benchmark bot after successful **main** collects and served at `/benchmarks/benchmark-data.json`.

## Profiles (speed vs quality)

| Profile | When | Go `-count` | k6 | Path | Proxy HTTP bench |
| --- | --- | --- | --- | --- | --- |
| `smoke` | Pull requests | 1 | 15 VUs / 15s | `GET /health` | skipped |
| `fast` | Daily cron (Mon–Sat), main pushes | 2 | 25 VUs / 30s | `GET /health` | yes |
| `full` | Sunday cron, `workflow_dispatch` | 5 | 100 VUs / 2m | `POST /v1/chat/completions` (`K6_USE_CHAT=1`) | yes |

Target wall-clock: **~2–4 min** for `smoke` PRs, **~5–10 min** for `fast`, current quality bar for `full`. All keep Postgres + Redis + real proxy. Go stage microbenches run before stack start. Each published run records `profile: "smoke" | "fast" | "full"`.

Stack helper seeds the DB and exports `IBEX_DEV_TOKEN` / `IBEX_DEV_AGENT_ID`; `IBEX_LLM_MODE=mock` registers an immediate stub provider so chat returns **200**.

## Planned expansions (do not invent paths early)

| Concern | Preferred phase | Likely home (orientation) |
| --- | --- | --- |
| Memory vector search recall/latency benches (HNSW `ef_search`) | **3** | Under `services/memory/` (or promoted here with ADR) |
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

## Local quick run

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

## Data flow

1. `aggregate_metrics.py` writes `benchmarks/output/latest.json`.
2. `regression_gate.py` writes `gate-result.json` and enforces SLA/regression policy.
3. `build_benchmark_data.py` merges the latest run into `benchmark-data.json` schema v1 (includes `profile`).
4. `generate_badge.py` writes `badge.svg` from the latest run status.
5. On `main` (schedule, dispatch, or path-triggered push), CI notifies the benchmark bot, which opens a Signed-off-by data PR.
