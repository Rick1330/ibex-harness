import type { PageTree } from "fumadocs-core/server";

import {
  BENCHMARK_HUB_PAGE,
  CROSS_SUITE_COMPARE_PAGE,
  buildBenchmarkNavPages,
  suiteById,
  type SuiteNavPage,
} from "@/lib/benchmarks/suites";

export { BENCHMARK_SUITES } from "@/lib/benchmarks/suites";

function benchmarkPageItem(name: string, url: string): PageTree.Item {
  return {
    type: "page",
    name,
    url,
  };
}

/**
 * Nested suite/section folder — root:false so the full tree is listed
 * (Docs/Roadmap style). defaultOpen:false — PathSyncedSidebarFolder opens
 * only the section that contains the active path.
 */
function suiteFolder(
  name: string,
  pages: readonly SuiteNavPage[],
  options?: Readonly<{
    index?: SuiteNavPage;
  }>,
): PageTree.Folder {
  const index =
    options?.index ?? pages.find((page) => page.name === "Overview");
  return {
    type: "folder",
    name,
    root: false,
    defaultOpen: false,
    index: index ? benchmarkPageItem(index.name, index.url) : undefined,
    children: pages.map((page) => benchmarkPageItem(page.name, page.url)),
  };
}

const proxySuite = suiteById("proxy");
const hnswSuite = suiteById("hnsw");
const rankingSuite = suiteById("rankingQuality");
const writeSuite = suiteById("writePipeline");
const extractionSuite = suiteById("extractionQuality");

const hnswOverview = hnswSuite.navPages.find((page) => page.name === "Overview")!;
const rankingOverview = rankingSuite.navPages.find((page) => page.name === "Overview")!;
const writeOverview = writeSuite.navPages.find((page) => page.name === "Overview")!;
const extractionOverview = extractionSuite.navPages.find(
  (page) => page.name === "Overview",
)!;

const memoryFolder: PageTree.Folder = {
  type: "folder",
  name: "Memory",
  root: false,
  defaultOpen: false,
  index: benchmarkPageItem(hnswOverview.name, hnswOverview.url),
  children: [
    suiteFolder(hnswSuite.label, hnswSuite.navPages, { index: hnswOverview }),
    suiteFolder(rankingSuite.label, rankingSuite.navPages, {
      index: rankingOverview,
    }),
    suiteFolder(writeSuite.label, writeSuite.navPages, {
      index: writeOverview,
    }),
  ],
};

/**
 * Full nested tree (no root switcher). Folders start collapsed; the active
 * path's ancestors expand via PathSyncedSidebarFolder / defaultOpen rules.
 */
export const benchmarkPageTree: PageTree.Root = {
  name: "Benchmarks",
  children: [
    benchmarkPageItem(BENCHMARK_HUB_PAGE.name, BENCHMARK_HUB_PAGE.url),
    benchmarkPageItem(CROSS_SUITE_COMPARE_PAGE.name, CROSS_SUITE_COMPARE_PAGE.url),
    suiteFolder(proxySuite.label, proxySuite.navPages),
    memoryFolder,
    suiteFolder(extractionSuite.label, extractionSuite.navPages, {
      index: extractionOverview,
    }),
  ],
};

/** Flat leaf list for sitemap / mobile drawer (hub + all suite pages). */
export const BENCHMARK_NAV_PAGES: readonly SuiteNavPage[] = buildBenchmarkNavPages();
