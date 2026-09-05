import { describe, expect, it } from "vitest";
import { Brain, Gauge, LayoutDashboard, Target } from "lucide-react";

import { buildCrossSuiteCompareRows } from "@/lib/benchmarks/cross-suite-compare";
import {
  BENCHMARK_HUB_PAGE,
  buildBenchmarkFolderIcons,
  buildBenchmarkPageIcons,
  suiteForPathname,
} from "@/lib/benchmarks/suites";

describe("cross-suite compare matrix", () => {
  it("fills shared identity rows", () => {
    const rows = buildCrossSuiteCompareRows([
      {
        id: "proxy",
        label: "Proxy",
        shortSha: "aaaaaaa",
        status: "pass",
        timestamp: "2026-09-05T00:00:00Z",
        metrics: [{ label: "Proxy p99", value: "12.0 ms" }],
      },
      {
        id: "extractionQuality",
        label: "Extraction",
        shortSha: null,
        status: null,
        timestamp: null,
        metrics: [],
      },
      {
        id: "rankingQuality",
        label: "Ranking",
        shortSha: "bbbbbbb",
        status: "pass",
        timestamp: "2026-09-04T00:00:00Z",
        metrics: [{ label: "Precision@5", value: "100.0%" }],
      },
    ]);

    const sha = rows.find((row) => row.label === "Latest SHA");
    expect(sha?.cells.proxy).toBe("aaaaaaa");
    expect(sha?.cells.extractionQuality).toBe("—");
    expect(sha?.cells.rankingQuality).toBe("bbbbbbb");
  });

  it("leaves suite-only metrics as dashes for other suites", () => {
    const rows = buildCrossSuiteCompareRows([
      {
        id: "proxy",
        label: "Proxy",
        shortSha: "aaaaaaa",
        status: "pass",
        timestamp: "2026-09-05T00:00:00Z",
        metrics: [{ label: "Proxy p99", value: "12.0 ms" }],
      },
      {
        id: "rankingQuality",
        label: "Ranking",
        shortSha: "bbbbbbb",
        status: "pass",
        timestamp: "2026-09-04T00:00:00Z",
        metrics: [{ label: "Precision@5", value: "100.0%" }],
      },
    ]);

    const p99 = rows.find((row) => row.label === "Proxy p99");
    expect(p99?.cells.proxy).toBe("12.0 ms");
    expect(p99?.cells.rankingQuality).toBe("—");

    const precision = rows.find((row) => row.label === "Precision@5");
    expect(precision?.cells.rankingQuality).toBe("100.0%");
    expect(precision?.cells.proxy).toBe("—");
  });
});

describe("benchmark hub icons and path classification", () => {
  it("keeps Overview distinct from Proxy leaf icons", () => {
    const icons = buildBenchmarkPageIcons();
    expect(icons["/benchmarks"]).toBe(LayoutDashboard);
    expect(icons["/benchmarks"]).toBe(BENCHMARK_HUB_PAGE.icon);
    expect(icons["/benchmarks/latency"]).not.toBe(LayoutDashboard);
    expect(icons["/benchmarks/suites-compare"]).toBeTruthy();
  });

  it("keeps folder icons on suite/group names, not Overview leaf icons", () => {
    const folders = buildBenchmarkFolderIcons();
    expect(folders.Proxy).toBe(Gauge);
    expect(folders.Memory).toBe(Brain);
    expect(folders["Ranking quality"]).toBe(Target);
    expect(folders.HNSW).toBe(Brain);
  });

  it("does not classify suites-compare as Proxy", () => {
    expect(suiteForPathname("/benchmarks/suites-compare")).toBeNull();
    expect(suiteForPathname("/benchmarks/latency")?.id).toBe("proxy");
    expect(suiteForPathname("/benchmarks/memory")?.id).toBe("hnsw");
  });
});
