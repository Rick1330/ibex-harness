import { z } from "zod";

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
});

const stageLatencySchema = z.object({
  auth_lru_p99_ms: z.number(),
  auth_grpc_p99_ms: z.number(),
  rate_limit_p99_ms: z.number(),
  directive_resolve_p99_ms: z.number(),
  prompt_inject_p99_ms: z.number(),
  total_overhead_p99_ms: z.number(),
});

const benchmarkRunSchema = z.object({
  sha: z.string(),
  short_sha: z.string(),
  timestamp: z.string(),
  branch: z.string(),
  pr_number: z.number().nullable(),
  run_url: z.string(),
  go_version: z.string(),
  runner_os: z.string(),
  runner_cpu: z.string(),
  runner_vcpus: z.number(),
  k6: k6ResultSchema,
  stages: stageLatencySchema,
  status: z.enum(["pass", "regression", "fail", "unknown"]),
  regression_vs_baseline_pct: z.number().nullable(),
  baseline_sha: z.string().nullable(),
  go_benchmarks: z.record(
    z.string(),
    z.object({
      ns_per_op: z.number(),
      allocs_per_op: z.number(),
      bytes_per_op: z.number(),
    }),
  ),
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
