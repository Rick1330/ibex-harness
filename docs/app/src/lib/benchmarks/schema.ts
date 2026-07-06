import { z } from "zod";

import { GO_MICROBENCH_SYNTHETIC_STAGE_MODEL } from "./constants";

const throughputPointSchema = z.object({
  t_s: z.number(),
  req_per_s: z.number(),
});

const k6ResultSchema = z.object({
  vus: z.number(),
  duration_s: z.number(),
  p50_ms: z.number(),
  p95_ms: z.number(),
  p99_ms: z.number(),
  p999_ms: z.number(),
  req_per_s: z.number(),
  error_rate: z.number(),
  check_rate: z.number(),
  throughput_series: z.array(throughputPointSchema).optional(),
});

const stageLatencySchema = z
  .object({
    auth_lru_p99_ms: z.number(),
    auth_grpc_p99_ms: z.number(),
    rate_limit_p99_ms: z.number(),
    directive_resolve_p99_ms: z.number(),
    prompt_inject_p99_ms: z.number(),
    total_overhead_p99_ms: z.number(),
  })
  .catchall(z.number().optional());

const goBenchmarkSchema = z.object({
  ns_per_op: z.number(),
  allocs_per_op: z.number(),
  bytes_per_op: z.number(),
  samples: z.number(),
  ci_95_low: z.number(),
  ci_95_high: z.number(),
  geomean_ns: z.number(),
});

const benchmarkRunSchema = z.object({
  sha: z.string(),
  short_sha: z.string(),
  timestamp: z.string(),
  branch: z.string(),
  pr_number: z.number().nullable(),
  run_number: z.number(),
  run_url: z.string(),
  go_version: z.string(),
  runner_os: z.string(),
  runner_cpu: z.string(),
  runner_vcpus: z.number(),
  runner_ram_gb: z.number(),
  k6_version: z.string(),
  k6: k6ResultSchema,
  stages: stageLatencySchema,
  status: z.enum(["pass", "regression", "fail", "unknown"]),
  regression_vs_baseline_pct: z.number().nullable(),
  baseline_sha: z.string().nullable(),
  metric_deltas: z.record(z.string(), z.number().nullable()),
  go_benchmarks: z.record(z.string(), goBenchmarkSchema),
  stage_model: z.literal(GO_MICROBENCH_SYNTHETIC_STAGE_MODEL).nullable().optional(),
});

export const benchmarkDataSchema = z.object({
  schema_version: z.literal(1),
  baseline_sha: z.string(),
  runs: z.array(benchmarkRunSchema),
});

export type BenchmarkDataParsed = z.infer<typeof benchmarkDataSchema>;

export function parseBenchmarkData(input: unknown): BenchmarkDataParsed {
  return benchmarkDataSchema.parse(input);
}
