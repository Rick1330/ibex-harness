import { flattenError } from "zod";

import publishedHnswBenchmarkData from "../../../public/benchmarks/hnsw-benchmark-data.json";

import { hnswBenchmarkDataSchema, type HnswBenchmarkDataParsed } from "./hnsw-schema";

const EMPTY: HnswBenchmarkDataParsed = {
  schema_version: 1,
  benchmark: "hnsw_recall_latency",
  runs: [],
};

export function loadPublishedHnswBenchmarkData(): HnswBenchmarkDataParsed {
  const parsed = hnswBenchmarkDataSchema.safeParse(publishedHnswBenchmarkData);
  if (!parsed.success) {
    console.warn(
      "loadPublishedHnswBenchmarkData: schema validation failed",
      flattenError(parsed.error),
    );
    return EMPTY;
  }
  return parsed.data;
}
