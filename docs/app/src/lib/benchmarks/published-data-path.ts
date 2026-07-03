import { flattenError } from "zod";

import publishedBenchmarkData from "../../../public/benchmarks/benchmark-data.json";

import { benchmarkDataSchema } from "./schema";

export function loadPublishedBenchmarkRuns(): { short_sha: string }[] {
  const parsed = benchmarkDataSchema.safeParse(publishedBenchmarkData);
  if (!parsed.success) {
    console.warn(
      "loadPublishedBenchmarkRuns: benchmark data schema validation failed",
      flattenError(parsed.error),
    );
    return [];
  }
  return parsed.data.runs.map((run) => ({ short_sha: run.short_sha }));
}
