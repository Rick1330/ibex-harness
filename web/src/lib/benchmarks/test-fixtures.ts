import type { BenchmarkRun } from "@/lib/benchmarks/types";

export function sampleBenchmarkRun(overrides: Partial<BenchmarkRun> = {}): BenchmarkRun {
  return {
    sha: "bfc0a75c8e4f2a1b9d0e3f4a5b6c7d8e9f0a1b2c",
    short_sha: "bfc0a75",
    timestamp: "2026-07-02T13:38:00+00:00",
    branch: "main",
    pr_number: null,
    run_number: 1,
    run_url: "",
    go_version: "1.24.2",
    runner_os: "Linux",
    runner_cpu: "AMD",
    runner_vcpus: 2,
    runner_ram_gb: 8,
    k6_version: "0.53.0",
    k6: {
      vus: 100,
      duration_s: 120,
      p50_ms: 1,
      p95_ms: 2,
      p99_ms: 3,
      p999_ms: 4,
      req_per_s: 1000,
      error_rate: 0,
      check_rate: 1,
    },
    stages: {
      auth_lru_p99_ms: 0.1,
      auth_grpc_p99_ms: 0.2,
      rate_limit_p99_ms: 0.3,
      directive_resolve_p99_ms: 0.4,
      prompt_inject_p99_ms: 0.5,
      total_overhead_p99_ms: 1,
    },
    status: "pass",
    regression_vs_baseline_pct: null,
    baseline_sha: null,
    metric_deltas: {},
    go_benchmarks: {},
    ...overrides,
  };
}
