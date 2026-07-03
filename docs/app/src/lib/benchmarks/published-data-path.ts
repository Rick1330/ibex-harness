import publishedBenchmarkData from "../../../public/benchmarks/benchmark-data.json";

import type { BenchmarkData } from "./types";

export function loadPublishedBenchmarkRuns(): { short_sha: string }[] {
  const data = publishedBenchmarkData as Pick<BenchmarkData, "runs">;
  return (data.runs ?? []).map((run) => ({ short_sha: run.short_sha }));
}
