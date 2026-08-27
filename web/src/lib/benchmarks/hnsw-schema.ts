import { z } from "zod";

const hnswSizeResultSchema = z.object({
  corpus_size: z.number().int().positive(),
  query_count: z.number().int().positive(),
  recall_at_10: z.number().min(0).max(1),
  latency_ms_p50: z.number().nonnegative(),
  latency_ms_p95: z.number().nonnegative(),
  latency_ms_p99: z.number().nonnegative(),
  latency_ms_p95_ci_low: z.number().nonnegative().optional(),
  latency_ms_p95_ci_high: z.number().nonnegative().optional(),
  ef_search: z.number().int().positive(),
  min_similarity: z.number().min(0).max(1).optional(),
  iterative_scan: z.enum(["off", "relaxed_order", "strict_order"]).optional(),
  index_build_mode: z.enum(["incremental", "bulk"]).optional(),
  plan_node_type: z.string().optional(),
  plan_index_name: z.string().optional(),
  shared_hit_blocks: z.number().int().nonnegative().optional(),
  shared_read_blocks: z.number().int().nonnegative().optional(),
  idx_scan_delta: z.number().int().nonnegative().optional(),
  row_count_verified: z.number().int().nonnegative().optional(),
});

const hnswMethodologySchema = z
  .object({
    index: z.string().optional(),
    ef_search: z.number().optional(),
    dim: z.number().optional(),
    recall: z.string().optional(),
    latency: z.string().optional(),
  })
  .passthrough();

const hnswGateSummarySchema = z
  .object({
    recall_ok: z.boolean().optional(),
    recall_floor: z.number().min(0).max(1).optional(),
    worst_recall_at_10: z.number().min(0).max(1).optional(),
    has_1m: z.boolean().optional(),
    p95_1m_ok: z.boolean().optional(),
    p99_1m_ok: z.boolean().optional(),
    p95_ms_1m: z.number().nonnegative().optional(),
    p99_ms_1m: z.number().nonnegative().optional(),
    note: z.string().optional(),
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
  status: z.enum(["pass", "fail", "warn"]).optional(),
  gate_summary: hnswGateSummarySchema.optional(),
});

export const hnswBenchmarkDataSchema = z.object({
  schema_version: z.literal(1),
  benchmark: z.literal("hnsw_recall_latency"),
  runs: z.array(hnswRunSchema),
});

export type HnswBenchmarkDataParsed = z.infer<typeof hnswBenchmarkDataSchema>;
export type HnswBenchmarkRun = z.infer<typeof hnswRunSchema>;
export type HnswSizeResult = z.infer<typeof hnswSizeResultSchema>;
