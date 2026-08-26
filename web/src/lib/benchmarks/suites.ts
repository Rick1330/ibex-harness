/**
 * Bench suite registry — UI + data URLs only.
 * Collect/publish schemas stay per-suite (proxy vs HNSW vs future).
 */

export type BenchmarkSuiteId = "proxy" | "hnsw";

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
  label: "Memory",
  basePath: "/benchmarks/memory",
  dataUrl: "/benchmarks/hnsw-benchmark-data.json",
  navPages: [
    { name: "Overview", url: "/benchmarks/memory" },
    { name: "Latency", url: "/benchmarks/memory/latency" },
    { name: "History", url: "/benchmarks/memory/history" },
    { name: "Compare", url: "/benchmarks/memory/compare" },
  ],
};

export const BENCHMARK_SUITES: readonly BenchmarkSuite[] = [PROXY_SUITE, HNSW_SUITE];

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
