import type { StageLatency } from "./types";

export const SLA_TARGETS = {
  total_overhead_p99_ms: 20,
  auth_lru_hit_p99_ms: 1,
  auth_grpc_fallback_p99_ms: 50,
  rate_limit_p99_ms: 5,
  directive_resolve_p99_ms: 2,
  prompt_inject_p99_ms: 0.5,
} as const satisfies Partial<Record<keyof StageLatency | "auth_lru_hit_p99_ms" | "auth_grpc_fallback_p99_ms", number>>;

export const K6_TARGETS = {
  p99_ms: 20,
  error_rate: 0.001,
  req_per_s: 5000,
} as const;

export const REGRESSION_THRESHOLD_PCT = 10;
export const WARNING_THRESHOLD_PCT = 5;
export const MAX_HISTORY_RUNS = 365;
export const CHART_WINDOW_DEFAULT = 30;
export const CHART_OVERVIEW_DAYS = 14;

export const BENCHMARK_DATA_URL = "/benchmarks/benchmark-data.json";
