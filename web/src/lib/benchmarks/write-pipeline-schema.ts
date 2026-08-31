import { z } from "zod";

const writeMetricsSchema = z.object({
  latency_ms_p50: z.number().nonnegative(),
  latency_ms_p95: z.number().nonnegative(),
  latency_ms_p99: z.number().nonnegative(),
});

const writeRunSchema = z.object({
  sha: z.string().min(7),
  short_sha: z.string().min(7),
  timestamp: z.string(),
  branch: z.string(),
  run_number: z.number().int().nonnegative(),
  run_url: z.string(),
  iterations: z.number().int().positive().optional(),
  metrics: writeMetricsSchema,
  status: z.enum(["pass", "fail"]).optional(),
  gate_summary: z.object({}).passthrough().optional(),
});

export const writePipelineBenchmarkDataSchema = z.object({
  schema_version: z.literal(1),
  benchmark: z.literal("write_pipeline"),
  runs: z.array(writeRunSchema),
});

export type WritePipelineBenchmarkDataParsed = z.infer<
  typeof writePipelineBenchmarkDataSchema
>;
export type WritePipelineBenchmarkRun = z.infer<typeof writeRunSchema>;
