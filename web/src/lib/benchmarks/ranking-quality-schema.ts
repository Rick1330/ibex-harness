import { z } from "zod";

import { memorySuiteDataSchema } from "./memory-suite-schema";

const rankingMetricsSchema = z.object({
  precision_at_5: z.number().min(0).max(1),
  recall_at_10: z.number().min(0).max(1),
  mrr: z.number().min(0).max(1),
  expected_order_match: z.number().min(0).max(1).optional(),
  top_category_accuracy: z.number().min(0).max(1).optional(),
});

const rankingRunShape = {
  gold_set: z.string().optional(),
  query_count: z.number().int().nonnegative().optional(),
  memory_count: z.number().int().nonnegative().optional(),
  metrics: rankingMetricsSchema,
} satisfies z.ZodRawShape;

export const rankingQualityBenchmarkDataSchema = memorySuiteDataSchema(
  "ranking_quality",
  rankingRunShape,
);

export type RankingQualityBenchmarkDataParsed = z.infer<
  typeof rankingQualityBenchmarkDataSchema
>;
export type RankingQualityBenchmarkRun =
  RankingQualityBenchmarkDataParsed["runs"][number];
