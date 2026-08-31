import { z } from "zod";

const rankingMetricsSchema = z.object({
  precision_at_5: z.number().min(0).max(1),
  recall_at_10: z.number().min(0).max(1),
  mrr: z.number().min(0).max(1),
  expected_order_match: z.number().min(0).max(1).optional(),
  top_category_accuracy: z.number().min(0).max(1).optional(),
});

const rankingRunSchema = z.object({
  sha: z.string().min(7),
  short_sha: z.string().min(7),
  timestamp: z.string(),
  branch: z.string(),
  run_number: z.number().int().nonnegative(),
  run_url: z.string(),
  gold_set: z.string().optional(),
  query_count: z.number().int().nonnegative().optional(),
  memory_count: z.number().int().nonnegative().optional(),
  metrics: rankingMetricsSchema,
  status: z.enum(["pass", "fail"]).optional(),
  gate_summary: z.object({}).passthrough().optional(),
});

export const rankingQualityBenchmarkDataSchema = z.object({
  schema_version: z.literal(1),
  benchmark: z.literal("ranking_quality"),
  runs: z.array(rankingRunSchema),
});

export type RankingQualityBenchmarkDataParsed = z.infer<
  typeof rankingQualityBenchmarkDataSchema
>;
export type RankingQualityBenchmarkRun = z.infer<typeof rankingRunSchema>;
