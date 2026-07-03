import path from "node:path";

const PUBLISHED_DIR = path.resolve(process.cwd(), "public", "benchmarks");
const BENCHMARK_DATA_FILENAME = "benchmark-data.json";

export function resolvePublishedBenchmarkDataPath(): string {
  const resolved = path.resolve(PUBLISHED_DIR, BENCHMARK_DATA_FILENAME);
  if (!resolved.startsWith(PUBLISHED_DIR)) {
    throw new Error("benchmark data path escapes published directory");
  }
  return resolved;
}
