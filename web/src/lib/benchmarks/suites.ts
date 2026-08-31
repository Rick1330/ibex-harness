/**
 * Bench suite registry — UI + data URLs only.
 * Collect/publish schemas stay per-suite (proxy vs HNSW vs ranking vs write).
 */

export type BenchmarkSuiteId = "proxy" | "hnsw" | "rankingQuality" | "writePipeline";

export type SuiteNavPage = Readonly<{
  name: string;
  url: string;
}>;

export type BenchmarkSuite = Readonly<{
  id: BenchmarkSuiteId;
  label: string;
  basePath: string;
  dataUrl: string;
  navPages: readonly SuiteNavPage[];
}>;

export const PROXY_SUITE: BenchmarkSuite = {
  id: "proxy",
  label: "Proxy",
  basePath: "/benchmarks",
  dataUrl: "/benchmarks/benchmark-data.json",
  navPages: [
    { name: "Latency", url: "/benchmarks/latency" },
    { name: "Waterfall", url: "/benchmarks/waterfall" },
    { name: "Load test", url: "/benchmarks/load" },
    { name: "History", url: "/benchmarks/history" },
    { name: "Compare", url: "/benchmarks/compare" },
  ],
};

export const HNSW_SUITE: BenchmarkSuite = {
  id: "hnsw",
  label: "Memory HNSW",
  basePath: "/benchmarks/memory",
  dataUrl: "/benchmarks/hnsw-benchmark-data.json",
  navPages: [
    { name: "Overview", url: "/benchmarks/memory" },
    { name: "Latency", url: "/benchmarks/memory/latency" },
    { name: "History", url: "/benchmarks/memory/history" },
    { name: "Compare", url: "/benchmarks/memory/compare" },
  ],
};

export const RANKING_QUALITY_SUITE: BenchmarkSuite = {
  id: "rankingQuality",
  label: "Ranking quality",
  basePath: "/benchmarks/memory/ranking-quality",
  dataUrl: "/benchmarks/ranking-quality-benchmark-data.json",
  navPages: [
    { name: "Overview", url: "/benchmarks/memory/ranking-quality" },
    { name: "History", url: "/benchmarks/memory/ranking-quality/history" },
  ],
};

export const WRITE_PIPELINE_SUITE: BenchmarkSuite = {
  id: "writePipeline",
  label: "Write pipeline",
  basePath: "/benchmarks/memory/write-pipeline",
  dataUrl: "/benchmarks/write-pipeline-benchmark-data.json",
  navPages: [
    { name: "Overview", url: "/benchmarks/memory/write-pipeline" },
    { name: "History", url: "/benchmarks/memory/write-pipeline/history" },
  ],
};

export const BENCHMARK_SUITES: readonly BenchmarkSuite[] = [
  PROXY_SUITE,
  HNSW_SUITE,
  RANKING_QUALITY_SUITE,
  WRITE_PIPELINE_SUITE,
];

/** Hub page — suite-aware overview (not nested under Proxy). */
export const BENCHMARK_HUB_PAGE: SuiteNavPage = {
  name: "Overview",
  url: "/benchmarks",
};

export function suiteById(id: BenchmarkSuiteId): BenchmarkSuite {
  const suite = BENCHMARK_SUITES.find((s) => s.id === id);
  if (!suite) {
    throw new Error(`Unknown benchmark suite: ${id}`);
  }
  return suite;
}
