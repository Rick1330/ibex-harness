import { describe, expect, it } from "vitest";

import { BENCHMARK_NAV_PAGES } from "@/lib/benchmark-page-tree";
import { stagePercentileRows } from "@/lib/benchmarks/stage-metrics";
import type { StageLatency } from "@/lib/benchmarks/types";

describe("benchmark navigation", () => {
  it("lists six sidebar destinations including compare", () => {
    expect(BENCHMARK_NAV_PAGES).toHaveLength(6);
    expect(BENCHMARK_NAV_PAGES.map((page) => page.url)).toContain("/benchmarks/compare");
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
