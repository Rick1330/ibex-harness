import { flattenError } from "zod";

import publishedHnswBenchmarkData from "../../../public/benchmarks/hnsw-benchmark-data.json";

import { hnswBenchmarkDataSchema, type HnswBenchmarkDataParsed } from "./hnsw-schema";

export type HnswPublishedLoadResult =
  | { readonly ok: true; readonly data: HnswBenchmarkDataParsed }
  | { readonly ok: false; readonly error: string };

const EMPTY: HnswBenchmarkDataParsed = {
  schema_version: 1,
  benchmark: "hnsw_recall_latency",
  runs: [],
};

export function loadPublishedHnswBenchmarkData(): HnswPublishedLoadResult {
  const parsed = hnswBenchmarkDataSchema.safeParse(publishedHnswBenchmarkData);
  if (!parsed.success) {
    const detail = flattenError(parsed.error);
    console.warn("loadPublishedHnswBenchmarkData: schema validation failed", detail);
    return {
      ok: false,
      error: "Published HNSW benchmark data failed schema validation.",
    };
  }
  if (parsed.data.runs.length === 0) {
    return { ok: true, data: EMPTY };
  }
  return { ok: true, data: parsed.data };
}
