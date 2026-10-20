# Benchmark baseline policy

The benchmark baseline is pinned by `benchmarks/data-schema/baseline.json`.

- `proxy_overhead_p99_ms` is the hard SLA target and should remain `< 20ms`; it is a policy ceiling, not a measured percentile.
- `max_regression_pct` is set to `20%` and applies to the pinned `synthetic_rate_limit_us` stage baseline. k6 p99 is gated absolutely against the SLA, never as a percentage of a cross-run value.
- `synthetic_rate_limit_us` is the measured `BenchmarkStageRateLimit` mean (ns/op → µs) for the hierarchical Lua limiter stage. The regression gate fails when latest `stages.synthetic_rate_limit_us` is missing/zero or when `%Δ` vs this pin exceeds `max_regression_pct`. This is a stage microbench envelope (miniredis), not a full-path SLA — full proxy overhead remains the Phase 2 **p99 &lt; 20ms** gate.
- Baseline updates must happen in an explicit PR with rationale and measurement notes.

When intentionally updating the baseline:

1. Run benchmark workflow manually on `main` (or locally: `go test ./benchmarks/go -bench=BenchmarkStageRateLimit -benchtime=3s -count=5`).
2. Convert mean `ns/op` to µs (`ns/op / 1000`) and set `baseline.synthetic_rate_limit_us`.
3. Validate the stage regression is expected and acceptable (k6 p99 remains ≤ 20ms on the same run).
4. Update `target_commit` / `baseline_sha` and other baseline values in `baseline.json` as needed.
5. Include justification and raw bench numbers in the PR description.

Do **not** hand-edit `web/public/benchmarks/benchmark-data.json`; `benchmark.yml` republishes history from aggregated runs.

## PR-time Go benchmark gate

The blocking `benchmark-gate` job in `.github/workflows/ci.yml` (wired into `ci-gate-go`) compares PR-head medians with a fresh base-branch run **on the same runner**:

- Base ref: `origin/<base_ref>` (normally `origin/main`), checked out into a temporary git worktree after the head run.
- Samples: 5 per benchmark; the gate uses the median `ns/op`, `B/op`, and `allocs/op`.
- Tolerance: 20% regression; missing or malformed benchmark output fails the job.
- Scope: `BenchmarkProxyOverhead` (warm proxy stage path) and `BenchmarkProxyChatOverhead` (full mock-provider chat).
- This is relative, same-runner evidence for warm-path **means**, not p99. The scheduled/manual full-chat k6 profile is the p99 measurement path; no recent passing full-chat run is in the published history.

No numeric cross-runner baseline is pinned for this gate. Pinning one would import runner speed (observed multi-run variance of 2–3x) into the policy; the base run is the control. Gate evidence is uploaded as the `go-benchmark-gate` artifact and includes the `base_ref` and tolerance.

The same caution applies to k6: PR comments use the PR's selected profile (normally `smoke`), while main/PR data publishes use `fast`/`full`. Local, PR, and hosted p99 values are not interchangeable; compare only runs from the same profile and environment, and use the absolute `< 20ms` SLO for pass/fail.
