import { z } from "zod";

import { benchmarkRunUrlSchema } from "./run-url";

const shaSchema = z.string().min(7);
const runNumberSchema = z.number().int().nonnegative();
const gateSummarySchema = z.object({}).passthrough().optional();
const statusSchema = z.enum(["pass", "fail"]).optional();

export function memorySuiteDataSchema<TBenchmark extends string, TRun extends z.ZodRawShape>(
  benchmark: TBenchmark,
  runShape: TRun,
) {
  const runSchema = z.object({
    sha: shaSchema,
    short_sha: shaSchema,
    timestamp: z.string(),
    branch: z.string(),
    run_number: runNumberSchema,
    run_url: benchmarkRunUrlSchema,
    status: statusSchema,
    gate_summary: gateSummarySchema,
    ...runShape,
  });

  return z.object({
    schema_version: z.literal(1),
    benchmark: z.literal(benchmark),
    runs: z.array(runSchema),
  });
}
