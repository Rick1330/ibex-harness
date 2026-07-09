import type { PageTree } from "fumadocs-core/server";

const BENCHMARK_PAGES = [
  { name: "Overview", url: "/benchmarks" },
  { name: "Latency", url: "/benchmarks/latency" },
  { name: "Waterfall", url: "/benchmarks/waterfall" },
  { name: "Load test", url: "/benchmarks/load" },
  { name: "History", url: "/benchmarks/history" },
  { name: "Compare", url: "/benchmarks/compare" },
] as const;

function benchmarkPageItem(
  name: string,
  url: string,
): PageTree.Item {
  return {
    type: "page",
    name,
    url,
  };
}

export const benchmarkPageTree: PageTree.Root = {
  name: "Benchmarks",
  children: BENCHMARK_PAGES.map((page) => benchmarkPageItem(page.name, page.url)),
};

export const BENCHMARK_NAV_PAGES = BENCHMARK_PAGES;
