import { z } from "zod";

export const contextAssemblyBenchmarkDataSchema = z.object({
  profile: z.literal("stub"),
  rps: z.number().min(1).refine(Number.isInteger),
  duration_s: z.number().positive(),
  attempted: z.number().nonnegative().refine(Number.isInteger),
  succeeded: z.number().nonnegative().refine(Number.isInteger),
  failed: z.number().nonnegative().refine(Number.isInteger),
  error_rate: z.number().min(0).max(1),
  mean_ms: z.number().nonnegative(),
  p50_ms: z.number().nonnegative(),
  p95_ms: z.number().nonnegative(),
  p99_ms: z.number().nonnegative(),
}).strict();

export type ContextAssemblyBenchmarkDataParsed = z.infer<
  typeof contextAssemblyBenchmarkDataSchema
>;
