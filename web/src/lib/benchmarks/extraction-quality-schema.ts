import { z } from "zod";

import { memorySuiteDataSchema } from "./memory-suite-schema";

const extractionMetricsSchema = z.object({
  precision_macro: z.number().min(0).max(1),
  recall_macro: z.number().min(0).max(1),
  category_assignment_accuracy: z.number().min(0).max(1),
  temporal_field_accuracy: z.number().min(0).max(1),
  precision_factual: z.number().min(0).max(1).optional(),
  recall_factual: z.number().min(0).max(1).optional(),
  precision_preference: z.number().min(0).max(1).optional(),
  recall_preference: z.number().min(0).max(1).optional(),
  precision_behavioral: z.number().min(0).max(1).optional(),
  recall_behavioral: z.number().min(0).max(1).optional(),
  precision_episodic: z.number().min(0).max(1).optional(),
  recall_episodic: z.number().min(0).max(1).optional(),
  precision_procedural: z.number().min(0).max(1).optional(),
  recall_procedural: z.number().min(0).max(1).optional(),
});

const extractionRunShape = {
  gold_set: z.string().optional(),
  conversation_count: z.number().int().nonnegative().optional(),
  provider: z.string().optional(),
  enforcement: z.enum(["ci", "manual"]).optional(),
  mode: z.string().optional(),
  model: z.string().nullable().optional(),
  metrics: extractionMetricsSchema,
} satisfies z.ZodRawShape;

export const extractionQualityBenchmarkDataSchema = memorySuiteDataSchema(
  "extraction_quality",
  extractionRunShape,
);

export type ExtractionQualityBenchmarkDataParsed = z.infer<
  typeof extractionQualityBenchmarkDataSchema
>;
export type ExtractionQualityBenchmarkRun =
  ExtractionQualityBenchmarkDataParsed["runs"][number];
