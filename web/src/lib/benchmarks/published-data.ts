import { flattenError } from "zod";

import publishedBenchmarkData from "../../../public/benchmarks/benchmark-data.json";

import { benchmarkDataSchema } from "./schema";
import type { BenchmarkData } from "./types";

const EMPTY_BENCHMARK_DATA: BenchmarkData = {
  schema_version: 1,
  baseline_sha: "",
  runs: [],
};

export function loadPublishedBenchmarkData(): BenchmarkData {
  const parsed = benchmarkDataSchema.safeParse(publishedBenchmarkData);
  if (!parsed.success) {
    console.warn(
      "loadPublishedBenchmarkData: benchmark data schema validation failed",
      flattenError(parsed.error),
    );
    return EMPTY_BENCHMARK_DATA;
  }
  return parsed.data;
}

export function loadPublishedBenchmarkRuns(): { short_sha: string }[] {
  return loadPublishedBenchmarkData().runs.map((run) => ({ short_sha: run.short_sha }));
}
