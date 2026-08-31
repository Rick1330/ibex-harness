import { z } from "zod";

import { memorySuiteDataSchema } from "./memory-suite-schema";

const writeMetricsSchema = z.object({
  latency_ms_p50: z.number().nonnegative(),
  latency_ms_p95: z.number().nonnegative(),
  latency_ms_p99: z.number().nonnegative(),
});

const writeRunShape = {
  iterations: z.number().int().positive().optional(),
  metrics: writeMetricsSchema,
} satisfies z.ZodRawShape;

export const writePipelineBenchmarkDataSchema = memorySuiteDataSchema(
  "write_pipeline",
  writeRunShape,
);

export type WritePipelineBenchmarkDataParsed = z.infer<
  typeof writePipelineBenchmarkDataSchema
>;
export type WritePipelineBenchmarkRun =
  WritePipelineBenchmarkDataParsed["runs"][number];
