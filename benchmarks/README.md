# Benchmarks

This directory contains the benchmark pipeline assets:

- `go/`: synthetic stage microbenchmarks for proxy overhead decomposition.
- `services/proxy/internal/http`: real `/health` handler benchmarks (`BenchmarkProxyHealth`).
- `k6/`: load test script against the real proxy `/health` endpoint.
- `scripts/`: aggregation, regression gate, published data builders, and proxy stack helpers.
- `data-schema/`: baseline policy, JSON schema, and benchmark data contracts.
- `testdata/`: fixtures for pipeline verification tests.

Published benchmark data is committed to `web/public/benchmarks/` on successful `main` runs and served by the docs site at `/benchmarks/benchmark-data.json`. Phase 2 adds the Next.js `/benchmarks` dashboard UI.

## Verification

```bash
go test ./benchmarks/go/...
python benchmarks/scripts/test_pipeline.py
cd web && npm test -- src/lib/benchmarks/ && npm run typecheck
```

## Local quick run

```bash
go test ./benchmarks/go -run=^$ -bench=. -benchmem -count=5 > benchmarks/output/go-bench.txt
go test ./services/proxy/internal/http -run=^$ -bench=BenchmarkProxy -benchmem -count=5 >> benchmarks/output/go-bench.txt
```

Load benchmarks require a running proxy stack:

```bash
bash benchmarks/scripts/start_proxy_stack.sh
docker run --rm --network host -v "$PWD:/work" -w /work \
  -e BASE_URL=http://127.0.0.1:18082 -e K6_HEALTH_PATH=/health \
  grafana/k6:0.53.0 run benchmarks/k6/proxy_load.js \
  --summary-trend-stats="med,p(90),p(95),p(99),p(99.9),min,max" \
  --summary-export benchmarks/output/k6-summary.json
bash benchmarks/scripts/stop_proxy_stack.sh
python benchmarks/scripts/aggregate_metrics.py
python benchmarks/scripts/regression_gate.py
python benchmarks/scripts/build_benchmark_data.py
python benchmarks/scripts/generate_badge.py
```

## Data flow

1. `aggregate_metrics.py` writes `benchmarks/output/latest.json`.
2. `regression_gate.py` writes `gate-result.json` and enforces SLA/regression policy.
3. `build_benchmark_data.py` merges the latest run into `benchmark-data.json` schema v1.
4. `generate_badge.py` writes `badge.svg` from the latest run status.
5. On `main`, CI commits `web/public/benchmarks/*` and triggers docs deploy.
