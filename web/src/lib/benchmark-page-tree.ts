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
const rankingSuite = BENCHMARK_SUITES.find((s) => s.id === "rankingQuality")!;
const writeSuite = BENCHMARK_SUITES.find((s) => s.id === "writePipeline")!;

const memoryFolder: PageTree.Folder = {
  type: "folder",
  name: "Memory",
  root: true,
  defaultOpen: true,
  index: benchmarkPageItem(hnswSuite.navPages[0].name, hnswSuite.navPages[0].url),
  children: [
    suiteFolder(hnswSuite.label, hnswSuite.navPages.slice(1)),
    suiteFolder(rankingSuite.label, rankingSuite.navPages, rankingSuite.navPages[0]),
    suiteFolder(writeSuite.label, writeSuite.navPages, writeSuite.navPages[0]),
  ],
};

export const benchmarkPageTree: PageTree.Root = {
  name: "Benchmarks",
  children: [
    benchmarkPageItem(BENCHMARK_HUB_PAGE.name, BENCHMARK_HUB_PAGE.url),
    suiteFolder(proxySuite.label, proxySuite.navPages),
    memoryFolder,
  ],
};

/** Flat leaf list for sitemap / mobile drawer (hub + all suite pages). */
export const BENCHMARK_NAV_PAGES: readonly SuiteNavPage[] = [
  BENCHMARK_HUB_PAGE,
  ...proxySuite.navPages,
  ...hnswSuite.navPages,
  ...rankingSuite.navPages,
  ...writeSuite.navPages,
];
