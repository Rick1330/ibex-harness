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

export const GO_MICROBENCH_SYNTHETIC_STAGE_MODEL = "go_microbench_synthetic" as const;
export const GO_MICROBENCH_WARM_PATH_STAGE_MODEL = "go_microbench_warm_path" as const;
export const GO_MICROBENCH_STAGE_MODEL = GO_MICROBENCH_WARM_PATH_STAGE_MODEL;

export const BENCHMARK_DATA_URL = "/benchmarks/benchmark-data.json";
export const HNSW_BENCHMARK_DATA_URL = "/benchmarks/hnsw-benchmark-data.json";
export const RANKING_QUALITY_BENCHMARK_DATA_URL =
  "/benchmarks/ranking-quality-benchmark-data.json";
export const WRITE_PIPELINE_BENCHMARK_DATA_URL =
  "/benchmarks/write-pipeline-benchmark-data.json";
export const EXTRACTION_QUALITY_BENCHMARK_DATA_URL =
  "/benchmarks/extraction-quality-benchmark-data.json";

/** Track B / Track E HNSW SLAs (roadmap + published gate_summary). */
export const HNSW_SLA_TARGETS = {
  recall_at_10: 0.98,
  p95_ms_1m: 30,
  p99_ms_1m: 100,
} as const;

export const RANKING_QUALITY_SLA_TARGETS = {
  precision_at_5: 1.0,
  recall_at_10: 1.0,
  mrr: 1.0,
} as const;

export const WRITE_PIPELINE_SLA_TARGETS = {
  latency_ms_p95: 200,
} as const;

export const EXTRACTION_QUALITY_SLA_TARGETS = {
  precision_macro: 1.0,
  recall_macro: 1.0,
  category_assignment_accuracy: 1.0,
  temporal_field_accuracy: 1.0,
} as const;
