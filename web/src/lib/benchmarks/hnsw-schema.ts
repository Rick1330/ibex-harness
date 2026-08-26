import { z } from "zod";

const hnswSizeResultSchema = z
  .object({
    corpus_size: z.number().int().positive(),
    query_count: z.number().int().positive(),
    recall_at_10: z.number().min(0).max(1),
    latency_ms_p50: z.number().nonnegative(),
    latency_ms_p95: z.number().nonnegative(),
    latency_ms_p99: z.number().nonnegative(),
    ef_search: z.number().int().positive(),
  })
  .passthrough();

const hnswMethodologySchema = z
  .object({
    index: z.string().optional(),
    ef_search: z.number().optional(),
    dim: z.number().optional(),
    recall: z.string().optional(),
    latency: z.string().optional(),
  })
  .passthrough();

const hnswRunSchema = z.object({
  sha: z.string().min(7),
  short_sha: z.string().min(7),
  timestamp: z.string(),
  branch: z.string(),
  run_number: z.number().int().nonnegative(),
  run_url: z.string(),
  methodology: hnswMethodologySchema,
  results: z.array(hnswSizeResultSchema).min(1),
  mean_recall_at_10: z.number().min(0).max(1),
});

export const hnswBenchmarkDataSchema = z.object({
  schema_version: z.literal(1),
  benchmark: z.literal("hnsw_recall_latency"),
  runs: z.array(hnswRunSchema),
});

export type HnswBenchmarkDataParsed = z.infer<typeof hnswBenchmarkDataSchema>;
export type HnswBenchmarkRun = z.infer<typeof hnswRunSchema>;
export type HnswSizeResult = z.infer<typeof hnswSizeResultSchema>;
