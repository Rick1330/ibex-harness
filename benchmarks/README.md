# Benchmarks

This directory contains the benchmark pipeline assets:

- `go/`: reproducible Go microbenchmarks for proxy overhead stages.
- `k6/`: load test script against the real proxy `/health` endpoint.
- `scripts/`: aggregation, gate, static-site build, and proxy stack helpers.
- `site/`: static multi-page dashboard published to `gh-pages`.
- `data-schema/`: baseline policy and schema-controlled benchmark data.
- `testdata/`: fixtures for pipeline verification tests.

## Verification

```bash
go test ./benchmarks/go/...
python benchmarks/scripts/test_pipeline.py
```

## Local quick run

```bash
go test ./benchmarks/go -run=^$ -bench=. -benchmem -count=5 > benchmarks/output/go-bench.txt
```

Load benchmarks require a running proxy stack:

```bash
bash benchmarks/scripts/start_proxy_stack.sh
docker run --rm --network host -v "$PWD:/work" -w /work \
  -e BASE_URL=http://127.0.0.1:18082 -e K6_HEALTH_PATH=/health \
  grafana/k6:0.53.0 run benchmarks/k6/proxy_load.js \
  --summary-export benchmarks/output/k6-summary.json
bash benchmarks/scripts/stop_proxy_stack.sh
```
