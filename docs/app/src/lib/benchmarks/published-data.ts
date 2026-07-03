import publishedBenchmarkData from "../../../public/benchmarks/benchmark-data.json";

import { parseBenchmarkData } from "./schema";
import type { BenchmarkData } from "./types";

export function loadPublishedBenchmarkData(): BenchmarkData {
  return parseBenchmarkData(publishedBenchmarkData);
}

export function loadPublishedBenchmarkRuns(): { short_sha: string }[] {
  return loadPublishedBenchmarkData().runs.map((run) => ({ short_sha: run.short_sha }));
}
