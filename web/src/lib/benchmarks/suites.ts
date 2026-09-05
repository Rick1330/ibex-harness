/**
 * Bench suite registry — UI + data URLs + nav metadata (single source of truth).
 * Collect/publish schemas stay per-suite (proxy vs HNSW vs ranking vs write).
 */

import {
  Activity,
  Brain,
  ClipboardCheck,
  Gauge,
  GitCompareArrows,
  History,
  LayoutDashboard,
  Layers,
  PenLine,
  Target,
  Zap,
  type LucideIcon,
} from "lucide-react";

export type BenchmarkSuiteId =
  | "proxy"
  | "hnsw"
  | "rankingQuality"
  | "writePipeline"
  | "extractionQuality";

export type BenchmarkGroupId = "proxy" | "memory" | "quality";

export type SuiteNavPage = Readonly<{
  name: string;
  url: string;
  icon: LucideIcon;
}>;

export type BenchmarkSuite = Readonly<{
  id: BenchmarkSuiteId;
  label: string;
  basePath: string;
  dataUrl: string;
  groupId: BenchmarkGroupId;
  icon: LucideIcon;
  navPages: readonly SuiteNavPage[];
}>;

export type BenchmarkGroup = Readonly<{
  id: BenchmarkGroupId;
  label: string;
  icon: LucideIcon;
  suiteIds: readonly BenchmarkSuiteId[];
}>;

/** Proxy detail pages; suite overview lives on the hub `/benchmarks` (Overview root). */
export const PROXY_SUITE: BenchmarkSuite = {
  id: "proxy",
  label: "Proxy",
  basePath: "/benchmarks",
  dataUrl: "/benchmarks/benchmark-data.json",
  groupId: "proxy",
  icon: Gauge,
  navPages: [
    { name: "Latency", url: "/benchmarks/latency", icon: Activity },
    { name: "Waterfall", url: "/benchmarks/waterfall", icon: Layers },
    { name: "Load test", url: "/benchmarks/load", icon: Zap },
    { name: "History", url: "/benchmarks/history", icon: History },
    { name: "Compare", url: "/benchmarks/compare", icon: GitCompareArrows },
  ],
};

export const HNSW_SUITE: BenchmarkSuite = {
  id: "hnsw",
  label: "HNSW",
  basePath: "/benchmarks/memory",
  dataUrl: "/benchmarks/hnsw-benchmark-data.json",
  groupId: "memory",
  icon: Brain,
  navPages: [
    { name: "Overview", url: "/benchmarks/memory", icon: LayoutDashboard },
    { name: "Latency", url: "/benchmarks/memory/latency", icon: Activity },
    { name: "History", url: "/benchmarks/memory/history", icon: History },
    { name: "Compare", url: "/benchmarks/memory/compare", icon: GitCompareArrows },
  ],
};

export const RANKING_QUALITY_SUITE: BenchmarkSuite = {
  id: "rankingQuality",
  label: "Ranking quality",
  basePath: "/benchmarks/memory/ranking-quality",
  dataUrl: "/benchmarks/ranking-quality-benchmark-data.json",
  groupId: "memory",
  icon: Target,
  navPages: [
    {
      name: "Overview",
      url: "/benchmarks/memory/ranking-quality",
      icon: LayoutDashboard,
    },
    {
      name: "History",
      url: "/benchmarks/memory/ranking-quality/history",
      icon: History,
    },
    {
      name: "Compare",
      url: "/benchmarks/memory/ranking-quality/compare",
      icon: GitCompareArrows,
    },
  ],
};

export const WRITE_PIPELINE_SUITE: BenchmarkSuite = {
  id: "writePipeline",
  label: "Write pipeline",
  basePath: "/benchmarks/memory/write-pipeline",
  dataUrl: "/benchmarks/write-pipeline-benchmark-data.json",
  groupId: "memory",
  icon: PenLine,
  navPages: [
    {
      name: "Overview",
      url: "/benchmarks/memory/write-pipeline",
      icon: LayoutDashboard,
    },
    {
      name: "History",
      url: "/benchmarks/memory/write-pipeline/history",
      icon: History,
    },
    {
      name: "Compare",
      url: "/benchmarks/memory/write-pipeline/compare",
      icon: GitCompareArrows,
    },
  ],
};

export const EXTRACTION_QUALITY_SUITE: BenchmarkSuite = {
  id: "extractionQuality",
  label: "Extraction quality",
  basePath: "/benchmarks/extraction-quality",
  dataUrl: "/benchmarks/extraction-quality-benchmark-data.json",
  groupId: "quality",
  icon: ClipboardCheck,
  navPages: [
    {
      name: "Overview",
      url: "/benchmarks/extraction-quality",
      icon: LayoutDashboard,
    },
    {
      name: "History",
      url: "/benchmarks/extraction-quality/history",
      icon: History,
    },
    {
      name: "Compare",
      url: "/benchmarks/extraction-quality/compare",
      icon: GitCompareArrows,
    },
  ],
};

export const BENCHMARK_SUITES: readonly BenchmarkSuite[] = [
  PROXY_SUITE,
  HNSW_SUITE,
  RANKING_QUALITY_SUITE,
  WRITE_PIPELINE_SUITE,
  EXTRACTION_QUALITY_SUITE,
];

export const BENCHMARK_GROUPS: readonly BenchmarkGroup[] = [
  { id: "proxy", label: "Proxy", icon: Gauge, suiteIds: ["proxy"] },
  {
    id: "memory",
    label: "Memory",
    icon: Brain,
    suiteIds: ["hnsw", "rankingQuality", "writePipeline"],
  },
  {
    id: "quality",
    label: "Quality",
    icon: ClipboardCheck,
    suiteIds: ["extractionQuality"],
  },
];

/**
 * Top-level hub leaf — `/benchmarks` overview.
 * Icon is LayoutDashboard so it stays distinct from Proxy (Gauge).
 */
export const BENCHMARK_HUB_PAGE: SuiteNavPage = {
  name: "Overview",
  url: "/benchmarks",
  icon: LayoutDashboard,
};

/** Cross-suite latest-run matrix (honest gaps with —). */
export const CROSS_SUITE_COMPARE_PAGE: SuiteNavPage = {
  name: "Suites compare",
  url: "/benchmarks/suites-compare",
  icon: GitCompareArrows,
};

export function suiteById(id: BenchmarkSuiteId): BenchmarkSuite {
  const suite = BENCHMARK_SUITES.find((s) => s.id === id);
  if (!suite) {
    throw new Error(`Unknown benchmark suite: ${id}`);
  }
  return suite;
}

export function suitesInGroup(groupId: BenchmarkGroupId): readonly BenchmarkSuite[] {
  const group = BENCHMARK_GROUPS.find((g) => g.id === groupId);
  if (!group) {
    return [];
  }
  return group.suiteIds.map((id) => suiteById(id));
}

function pathMatchesSuite(normalized: string, suite: BenchmarkSuite): boolean {
  if (normalized === suite.basePath) {
    return true;
  }
  if (normalized.startsWith(`${suite.basePath}/`)) {
    return true;
  }
  return suite.navPages.some((page) => page.url === normalized);
}

export function suiteForPathname(pathname: string): BenchmarkSuite | null {
  const normalized = pathname.replace(/\/$/, "") || "/benchmarks";
  // Cross-suite compare lives under `/benchmarks/` but is not Proxy.
  if (
    normalized === CROSS_SUITE_COMPARE_PAGE.url ||
    normalized.startsWith(`${CROSS_SUITE_COMPARE_PAGE.url}/`)
  ) {
    return null;
  }
  const ranked = [...BENCHMARK_SUITES].sort(
    (a, b) => b.basePath.length - a.basePath.length,
  );
  for (const suite of ranked) {
    if (pathMatchesSuite(normalized, suite)) {
      return suite;
    }
  }
  return null;
}

/** Flat leaf list for sitemap / mobile drawer (hub + all suite pages). Dedupes proxy hub URL. */
export function buildBenchmarkNavPages(): readonly SuiteNavPage[] {
  const pages: SuiteNavPage[] = [BENCHMARK_HUB_PAGE, CROSS_SUITE_COMPARE_PAGE];
  const seen = new Set<string>([BENCHMARK_HUB_PAGE.url, CROSS_SUITE_COMPARE_PAGE.url]);
  for (const suite of BENCHMARK_SUITES) {
    for (const page of suite.navPages) {
      if (seen.has(page.url)) {
        continue;
      }
      seen.add(page.url);
      pages.push(page);
    }
  }
  return pages;
}

function collectLeafPageIcons(): Record<string, LucideIcon> {
  const icons: Record<string, LucideIcon> = {};
  for (const suite of BENCHMARK_SUITES) {
    for (const page of suite.navPages) {
      icons[page.url] = page.icon;
    }
  }
  return icons;
}

/**
 * Leaf-page icons only. Folder headers use {@link buildBenchmarkFolderIcons}
 * so Overview (LayoutDashboard) does not overwrite suite/group folder icons.
 * Hub icon is applied last so it wins over any leaf that shares `/benchmarks`.
 */
export function buildBenchmarkPageIcons(): Record<string, LucideIcon> {
  return {
    ...collectLeafPageIcons(),
    [CROSS_SUITE_COMPARE_PAGE.url]: CROSS_SUITE_COMPARE_PAGE.icon,
    [BENCHMARK_HUB_PAGE.url]: BENCHMARK_HUB_PAGE.icon,
  };
}

/** Folder-header icons keyed by sidebar folder display name. */
export function buildBenchmarkFolderIcons(): Record<string, LucideIcon> {
  const icons: Record<string, LucideIcon> = {};
  for (const group of BENCHMARK_GROUPS) {
    icons[group.label] = group.icon;
  }
  for (const suite of BENCHMARK_SUITES) {
    icons[suite.label] = suite.icon;
  }
  return icons;
}
