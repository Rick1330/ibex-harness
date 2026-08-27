import type { PageTree } from "fumadocs-core/server";

import {
  BENCHMARK_HUB_PAGE,
  BENCHMARK_SUITES,
  type SuiteNavPage,
} from "@/lib/benchmarks/suites";

function benchmarkPageItem(name: string, url: string): PageTree.Item {
  return {
    type: "page",
    name,
    url,
  };
}

function suiteFolder(
  name: string,
  pages: readonly SuiteNavPage[],
  index?: SuiteNavPage,
): PageTree.Folder {
  return {
    type: "folder",
    name,
    root: true,
    defaultOpen: true,
    index: index ? benchmarkPageItem(index.name, index.url) : undefined,
    children: pages
      .filter((page) => index?.url !== page.url)
      .map((page) => benchmarkPageItem(page.name, page.url)),
  };
}

const proxySuite = BENCHMARK_SUITES.find((s) => s.id === "proxy")!;
const hnswSuite = BENCHMARK_SUITES.find((s) => s.id === "hnsw")!;

export const benchmarkPageTree: PageTree.Root = {
  name: "Benchmarks",
  children: [
    benchmarkPageItem(BENCHMARK_HUB_PAGE.name, BENCHMARK_HUB_PAGE.url),
    suiteFolder(proxySuite.label, proxySuite.navPages),
    suiteFolder(hnswSuite.label, hnswSuite.navPages, hnswSuite.navPages[0]),
  ],
};

/** Flat leaf list for sitemap / mobile drawer (hub + all suite pages). */
export const BENCHMARK_NAV_PAGES: readonly SuiteNavPage[] = [
  BENCHMARK_HUB_PAGE,
  ...proxySuite.navPages,
  ...hnswSuite.navPages,
];
