# Benchmarks

This directory contains the benchmark pipeline assets:

- `go/`: reproducible Go microbenchmarks for proxy overhead stages.
- `k6/`: load test script for request latency and throughput metrics.
- `scripts/`: aggregation, gate, and static-site build scripts.
- `site/`: static multi-page dashboard published to `gh-pages`.
- `data-schema/`: baseline policy and schema-controlled benchmark data.

Local quick run:

```bash
go test ./benchmarks/go -run=^$ -bench=. -benchmem -count=5 > benchmarks/output/go-bench.txt
```
