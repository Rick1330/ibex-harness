import { describe, expect, it } from "vitest";

import {
  deltaPctVsPrevious,
  filterSuiteRunsByRange,
  suiteRunsToTrendData,
} from "@/lib/benchmarks/suite-trend";

describe("suite-trend helpers", () => {
  const now = Date.now();
  const dayMs = 24 * 60 * 60 * 1000;
  const runs = [
    {
      timestamp: new Date(now - 1 * dayMs).toISOString(),
      short_sha: "aaaaaaa",
      status: "pass" as const,
      value: 1.0,
    },
    {
      timestamp: new Date(now - 20 * dayMs).toISOString(),
      short_sha: "bbbbbbb",
      status: "fail" as const,
      value: 0.5,
    },
  ];

  it("filters by range without inventing rows", () => {
    const filtered = filterSuiteRunsByRange(runs, "7d");
    expect(filtered).toHaveLength(1);
    expect(filtered[0]?.short_sha).toBe("aaaaaaa");
  });

  it("returns empty trend data for empty runs", () => {
    const empty: typeof runs = [];
    expect(suiteRunsToTrendData(empty, (run) => run.value)).toEqual([]);
  });

  it("maps metric accessor into trend points", () => {
    const data = suiteRunsToTrendData(runs, (run) => run.value);
    expect(data).toHaveLength(2);
    expect(data[0]?.shortSha).toBe("bbbbbbb");
    expect(data[1]?.value).toBe(1.0);
  });

  it("hides delta when previous is absent or zero", () => {
    expect(deltaPctVsPrevious(1, null)).toBeNull();
    expect(deltaPctVsPrevious(1, undefined)).toBeNull();
    expect(deltaPctVsPrevious(1, 0)).toBeNull();
    expect(deltaPctVsPrevious(1.1, 1)).toBeCloseTo(10);
  });
});
