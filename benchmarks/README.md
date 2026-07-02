# Benchmarks

This directory contains the benchmark pipeline assets:

- `go/`: synthetic stage microbenchmarks for proxy overhead decomposition.
- `services/proxy/internal/http`: real `/health` handler benchmarks (`BenchmarkProxyHealth`).
- `k6/`: load test script against the real proxy `/health` endpoint.
- `scripts/`: aggregation, gate, static-site build, and proxy stack helpers.
- `site/`: static multi-page dashboard (Matte Graphite theme) published to `gh-pages`.
- `data-schema/`: baseline policy and schema-controlled benchmark data.
- `testdata/`: fixtures for pipeline verification tests.

Brand marks are synced from `docs/app/public/brand/` at site build time.

## Verification

```bash
go test ./benchmarks/go/...
python benchmarks/scripts/test_pipeline.py
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
python benchmarks/scripts/build_site.py
```

k6 0.53 exports flat metric objects (no `values` wrapper). `aggregate_metrics.py` supports both legacy and v0.53 summary shapes.
