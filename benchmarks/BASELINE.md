# Benchmark baseline policy

The benchmark baseline is pinned by `benchmarks/data-schema/baseline.json`.

- `proxy_overhead_p99_ms` is the hard SLA target and should remain `< 20ms`.
- `max_regression_pct` is set to `20%` and is evaluated against the pinned baseline.
- Baseline updates must happen in an explicit PR with rationale and measurement notes.

When intentionally updating the baseline:

1. Run benchmark workflow manually on `main`.
2. Validate regressions are expected and acceptable.
3. Update `target_commit` and baseline values in `baseline.json`.
4. Include justification in PR description.
