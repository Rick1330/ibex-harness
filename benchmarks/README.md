# Benchmarks

This directory contains the benchmark pipeline assets:

- `go/`: proxy overhead stage microbenchmarks (ratelimit is real; other stages still synthetic until 2.6.1 / issue #291).
- `services/proxy/internal/http`: real `/health` handler benchmarks (`BenchmarkProxyHealth`).
- `k6/`: load test script against the real proxy `/health` endpoint.
- `scripts/`: aggregation, regression gate, published data builders, and proxy stack helpers.
- `data-schema/`: baseline policy, JSON schema, and benchmark data contracts.
- `testdata/`: fixtures for pipeline verification tests.

Published benchmark data is committed to `web/public/benchmarks/` via the benchmark bot after successful **main** collects and served at `/benchmarks/benchmark-data.json`.

## Profiles (speed vs quality)

| Profile | When | Go `-count` | k6 |
| --- | --- | --- | --- |
| `fast` | Daily cron (Mon–Sat), PRs, main pushes | 2 | 25 VUs / 30s |
| `full` | Sunday cron, `workflow_dispatch` | 5 | 100 VUs / 2m |

Target wall-clock: **~5–10 min** for `fast`, current quality bar for `full`. Both keep Postgres + Redis + real proxy stack. Each published run records `profile: "fast" | "full"`.

CI defaults remain `GET /health`; set `K6_USE_CHAT=1` for chat-path load once Phase 2 middleware is complete.

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
