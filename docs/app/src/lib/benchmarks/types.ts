export type RunStatus = "pass" | "regression" | "fail" | "unknown";

export interface ThroughputPoint {
  t_s: number;
  req_per_s: number;
}

export interface K6Result {
  vus: number;
  duration_s: number;
  p50_ms: number;
  p95_ms: number;
  p99_ms: number;
  p999_ms: number;
  req_per_s: number;
  error_rate: number;
  check_rate: number;
  throughput_series?: ThroughputPoint[];
}

export interface StageLatency {
  auth_lru_p99_ms: number;
  auth_lru_p50_ms?: number;
  auth_lru_p95_ms?: number;
  auth_lru_p999_ms?: number;
  auth_grpc_p99_ms: number;
  auth_grpc_p50_ms?: number;
  auth_grpc_p95_ms?: number;
  auth_grpc_p999_ms?: number;
  rate_limit_p99_ms: number;
  rate_limit_p50_ms?: number;
  rate_limit_p95_ms?: number;
  rate_limit_p999_ms?: number;
  directive_resolve_p99_ms: number;
  directive_resolve_p50_ms?: number;
  directive_resolve_p95_ms?: number;
  directive_resolve_p999_ms?: number;
  prompt_inject_p99_ms: number;
  prompt_inject_p50_ms?: number;
  prompt_inject_p95_ms?: number;
  prompt_inject_p999_ms?: number;
  total_overhead_p99_ms: number;
  total_overhead_p50_ms?: number;
  total_overhead_p95_ms?: number;
  total_overhead_p999_ms?: number;
}

export interface GoBenchmarkMetrics {
  ns_per_op: number;
  allocs_per_op: number;
  bytes_per_op: number;
  samples: number;
  ci_95_low: number;
  ci_95_high: number;
  geomean_ns: number;
}

export interface BenchmarkRun {
  sha: string;
  short_sha: string;
  timestamp: string;
  branch: string;
  pr_number: number | null;
  run_number: number;
  run_url: string;
  go_version: string;
  runner_os: string;
  runner_cpu: string;
  runner_vcpus: number;
  runner_ram_gb: number;
  k6_version: string;
  k6: K6Result;
  stages: StageLatency;
  status: RunStatus;
  regression_vs_baseline_pct: number | null;
  baseline_sha: string | null;
  metric_deltas: Record<string, number | null>;
  go_benchmarks: Record<string, GoBenchmarkMetrics>;
}

export interface BenchmarkData {
  schema_version: 1;
  baseline_sha: string;
  runs: BenchmarkRun[];
}
