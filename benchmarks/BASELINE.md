# Benchmark baseline policy

The benchmark baseline is pinned by `benchmarks/data-schema/baseline.json`.

- `proxy_overhead_p99_ms` is the hard SLA target and should remain `< 20ms`.
- `max_regression_pct` is set to `20%` and is evaluated against the pinned baseline.
- `synthetic_rate_limit_us` is the measured `BenchmarkStageRateLimit` mean (ns/op → µs) for the hierarchical Lua limiter stage. The regression gate fails when latest `stages.synthetic_rate_limit_us` is missing/zero or when `%Δ` vs this pin exceeds `max_regression_pct`. This is a stage microbench envelope (miniredis), not a full-path SLA — full proxy overhead remains the Phase 2 **p99 &lt; 20ms** gate.
- Baseline updates must happen in an explicit PR with rationale and measurement notes.

When intentionally updating the baseline:

1. Run benchmark workflow manually on `main` (or locally: `go test ./benchmarks/go -bench=BenchmarkStageRateLimit -benchtime=3s -count=5`).
2. Convert mean `ns/op` to µs (`ns/op / 1000`) and set `baseline.synthetic_rate_limit_us`.
3. Validate regressions are expected and acceptable (k6 p99 still ≤ 20ms).
4. Update `target_commit` / `baseline_sha` and other baseline values in `baseline.json` as needed.
5. Include justification and raw bench numbers in the PR description.

Do **not** hand-edit `web/public/benchmarks/benchmark-data.json`; `benchmark.yml` republishes history from aggregated runs.
