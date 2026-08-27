import { describe, expect, it } from "vitest";

import { buildHnswCompareMetricRows } from "@/lib/benchmarks/hnsw-compare-metrics";
import {
  corpusSizeLabel,
  filterHnswRunsByRange,
  findHnswRunByNumber,
  findHnswRunBySha,
  formatRecallPct,
  parseHnswRunNumber,
} from "@/lib/benchmarks/hnsw-runs";
import type { HnswBenchmarkRun } from "@/lib/benchmarks/hnsw-schema";

function sampleRun(overrides: Partial<HnswBenchmarkRun> = {}): HnswBenchmarkRun {
  return {
    sha: "abcdef0123456789",
    short_sha: "abcdef0",
    timestamp: "2026-08-26T12:00:00.000Z",
    branch: "main",
    run_number: 1,
    run_url: "",
    methodology: { ef_search: 40 },
    mean_recall_at_10: 1,
    results: [
      {
        corpus_size: 10_000,
        query_count: 500,
        recall_at_10: 1,
        latency_ms_p50: 10,
        latency_ms_p95: 20,
        latency_ms_p99: 22,
        ef_search: 40,
      },
    ],
    ...overrides,
  };
}

describe("hnsw-runs helpers", () => {
  it("formats corpus sizes and recall", () => {
    expect(corpusSizeLabel(10_000)).toBe("10K");
    expect(corpusSizeLabel(1_000_000)).toBe("1M");
    expect(formatRecallPct(0.98)).toBe("98.0%");
  });

  it("finds runs by short or full sha", () => {
    const runs = [sampleRun()];
    expect(findHnswRunBySha(runs, "abcdef0")?.run_number).toBe(1);
    expect(findHnswRunBySha(runs, "abcdef0123456789")?.short_sha).toBe("abcdef0");
  });

  it("finds runs by run_number when SHAs collide", () => {
    const first = sampleRun({ run_number: 1 });
    const second = sampleRun({ run_number: 2, timestamp: "2026-08-27T12:00:00.000Z" });
    expect(findHnswRunByNumber([first, second], 2)?.run_number).toBe(2);
    expect(findHnswRunByNumber([first, second], 9)).toBeNull();
  });

  it("parses only canonical run-number path segments", () => {
    expect(parseHnswRunNumber("0")).toBe(0);
    expect(parseHnswRunNumber("12")).toBe(12);
    expect(parseHnswRunNumber(String(Number.MAX_SAFE_INTEGER))).toBe(Number.MAX_SAFE_INTEGER);
    expect(parseHnswRunNumber(String(Number.MAX_SAFE_INTEGER + 1))).toBeNull();
    expect(parseHnswRunNumber("12x")).toBeNull();
    expect(parseHnswRunNumber("12.5")).toBeNull();
    expect(parseHnswRunNumber("012")).toBeNull();
    expect(parseHnswRunNumber("-1")).toBeNull();
    expect(parseHnswRunNumber("")).toBeNull();
  });

  it("filters by time range", () => {
    const old = sampleRun({
      sha: "1111111111111111",
      short_sha: "1111111",
      timestamp: "2020-01-01T00:00:00.000Z",
    });
    const recent = sampleRun();
    expect(filterHnswRunsByRange([old, recent], "14d")).toEqual([recent]);
  });
});

describe("buildHnswCompareMetricRows", () => {
  it("includes mean recall and per-size deltas", () => {
    const base = sampleRun({
      sha: "aaaaaaaaaaaaaaaa",
      short_sha: "aaaaaaa",
      mean_recall_at_10: 0.99,
      results: [
        {
          corpus_size: 10_000,
          query_count: 500,
          recall_at_10: 0.99,
          latency_ms_p50: 10,
          latency_ms_p95: 20,
          latency_ms_p99: 22,
          ef_search: 40,
        },
      ],
    });
    const head = sampleRun({ mean_recall_at_10: 1 });
    const rows = buildHnswCompareMetricRows(base, head);
    expect(rows[0]?.label).toBe("Mean recall@10");
    expect(rows.some((r) => r.label === "10K p95")).toBe(true);
  });
});
