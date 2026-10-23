import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/source", () => ({
  source: { getPages: () => [] },
  blogSource: { getPages: () => [] },
  roadmapSource: { getPages: () => [] },
}));

import sitemap from "@/app/sitemap";
import { BENCHMARK_NAV_PAGES, benchmarkPageTree } from "@/lib/benchmark-page-tree";
import {
  BENCHMARK_GROUPS,
  BENCHMARK_SUITES,
  buildBenchmarkNavPages,
  buildBenchmarkPageIcons,
  suiteById,
  suitesInGroup,
} from "@/lib/benchmarks/suites";
import { stagePercentileRows } from "@/lib/benchmarks/stage-metrics";
import type { StageLatency } from "@/lib/benchmarks/types";

function collectUrls(node: {
  type?: string;
  url?: string;
  index?: { url?: string };
  children?: readonly unknown[];
}): string[] {
  const urls: string[] = [];
  if (typeof node.url === "string") {
    urls.push(node.url);
  }
  if (node.index?.url) {
    urls.push(node.index.url);
  }
  for (const child of node.children ?? []) {
    urls.push(...collectUrls(child as Parameters<typeof collectUrls>[0]));
  }
  return urls;
}

describe("benchmark navigation", () => {
  it("resolves context assembly at its reserved data path and includes it in its group", () => {
    const suite = suiteById("contextAssembly");
    expect(suite.dataUrl).toBe("/benchmarks/context-assembly-benchmark-data.json");
    expect(suite.basePath).toBe("/benchmarks/context-assembly");
    expect(BENCHMARK_SUITES).toContain(suite);
    expect(BENCHMARK_GROUPS.find((group) => group.id === suite.groupId)?.suiteIds)
      .toContain("contextAssembly");
    expect(suitesInGroup(suite.groupId)).toContain(suite);
    expect(suite.navPages.map((page) => ({ name: page.name, url: page.url })))
      .toEqual([{ name: "Overview", url: "/benchmarks/context-assembly" }]);
  });

  it("withholds the registered context Overview from the sidebar and sitemap", () => {
    expect(collectUrls(benchmarkPageTree)).not.toContain("/benchmarks/context-assembly");
    expect(benchmarkPageTree.children.map((node) => node.name))
      .not.toContain("Context assembly");
    expect(buildBenchmarkNavPages().map((page) => page.url))
      .not.toContain("/benchmarks/context-assembly");
    expect(BENCHMARK_NAV_PAGES.map((page) => page.url))
      .not.toContain("/benchmarks/context-assembly");

    const sitemapPaths = sitemap().map((page) => new URL(page.url).pathname);
    expect(sitemapPaths).not.toContain("/benchmarks/context-assembly");
    expect(sitemapPaths).toContain("/benchmarks/extraction-quality");
  });

  it("exposes hub plus every available suite destination", () => {
    const urls = BENCHMARK_NAV_PAGES.map((page) => page.url);
    expect(urls).toContain("/benchmarks");
    expect(urls).not.toContain("/benchmarks/proxy");
    expect(urls).toContain("/benchmarks/latency");
    expect(urls).toContain("/benchmarks/compare");
    expect(urls).toContain("/benchmarks/memory");
    expect(urls).toContain("/benchmarks/memory/latency");
    expect(urls).toContain("/benchmarks/memory/history");
    expect(urls).toContain("/benchmarks/memory/compare");
    expect(urls).toContain("/benchmarks/memory/ranking-quality");
    expect(urls).toContain("/benchmarks/memory/ranking-quality/history");
    expect(urls).toContain("/benchmarks/memory/ranking-quality/compare");
    expect(urls).toContain("/benchmarks/memory/write-pipeline");
    expect(urls).toContain("/benchmarks/memory/write-pipeline/history");
    expect(urls).toContain("/benchmarks/memory/write-pipeline/compare");
    expect(urls).toContain("/benchmarks/extraction-quality");
    expect(urls).toContain("/benchmarks/extraction-quality/history");
    expect(urls).toContain("/benchmarks/extraction-quality/compare");
    expect(urls).toContain("/benchmarks/suites-compare");
    expect(urls).not.toContain("/benchmarks/context-assembly");
    // hub Overview + suites compare + 5 proxy + 4 hnsw + 3 ranking + 3 write + 3 extraction
    expect(BENCHMARK_NAV_PAGES).toHaveLength(20);
  });

  it("derives icons for every nav page url including ranking/write/extraction", () => {
    const icons = buildBenchmarkPageIcons();
    for (const page of BENCHMARK_NAV_PAGES) {
      expect(icons[page.url], `missing icon for ${page.url}`).toBeTruthy();
    }
    expect(icons["/benchmarks/memory/ranking-quality"]).toBeTruthy();
    expect(icons["/benchmarks/memory/write-pipeline"]).toBeTruthy();
    expect(icons["/benchmarks/extraction-quality"]).toBeTruthy();
    expect(icons["/benchmarks/extraction-quality/compare"]).toBeTruthy();
  });

  it("builds a page tree that includes every available suite overview", () => {
    const urls = collectUrls(benchmarkPageTree);
    expect(urls).toContain("/benchmarks");
    expect(urls).toContain("/benchmarks/memory");
    expect(urls).toContain("/benchmarks/memory/ranking-quality");
    expect(urls).toContain("/benchmarks/extraction-quality");
    for (const suite of BENCHMARK_SUITES) {
      if (suite.id === "proxy" || suite.id === "contextAssembly") {
        continue;
      }
      const overview = suite.navPages.find((page) => page.name === "Overview");
      expect(overview).toBeTruthy();
      expect(urls).toContain(overview!.url);
    }
  });

  it("lists Overview plus available suites in one nested tree (no root switcher)", () => {
    const roots = benchmarkPageTree.children.filter(
      (node) => node.type === "folder" && node.root,
    );
    expect(roots).toHaveLength(0);

    const topNames = benchmarkPageTree.children.map((node) => node.name);
    expect(topNames).toEqual([
      "Overview",
      "Suites compare",
      "Proxy",
      "Memory",
      "Extraction quality",
    ]);

    const memory = benchmarkPageTree.children.find((node) => node.name === "Memory");
    expect(memory?.type).toBe("folder");
    if (memory?.type === "folder") {
      expect(memory.root).toBe(false);
      expect(memory.index?.url).toBe("/benchmarks/memory");
      expect(memory.children.map((child) => child.name)).toEqual([
        "HNSW",
        "Ranking quality",
        "Write pipeline",
      ]);
    }
  });
});

describe("stagePercentileRows", () => {
  const stages: StageLatency = {
    auth_lru_p99_ms: 1,
    auth_lru_p50_ms: 0.5,
    auth_grpc_p99_ms: 0.2,
    rate_limit_p99_ms: 0.3,
    directive_resolve_p99_ms: 0.1,
    prompt_inject_p99_ms: 0.05,
    total_overhead_p99_ms: 2,
  };

  it("uses explicit percentiles when present", () => {
    const row = stagePercentileRows(stages, {
      auth_lru_p99_ms: "Auth",
    }).find((entry) => entry.base === "auth_lru");
    expect(row?.p50).toBe(0.5);
    expect(row?.p99).toBe(1);
  });

  it("leaves missing percentiles undefined", () => {
    const row = stagePercentileRows(stages, {
      auth_grpc_p99_ms: "Auth gRPC",
    }).find((entry) => entry.base === "auth_grpc");
    expect(row?.p50).toBeUndefined();
    expect(row?.p95).toBeUndefined();
    expect(row?.p999).toBeUndefined();
    expect(row?.p99).toBe(0.2);
  });

  it("leaves missing p99 undefined instead of fabricating zero", () => {
    const sparse = {
      auth_lru_p50_ms: 0.5,
      auth_grpc_p99_ms: 0,
      rate_limit_p99_ms: 0,
      directive_resolve_p99_ms: 0,
      prompt_inject_p99_ms: 0,
      total_overhead_p99_ms: 0,
    } as StageLatency;
    const row = stagePercentileRows(sparse, {
      auth_lru_p99_ms: "Auth",
    }).find((entry) => entry.base === "auth_lru");
    expect(row?.p50).toBe(0.5);
    expect(row?.p99).toBeUndefined();
  });
});
