import { formatDeltaPct, formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { pctChange } from "@/lib/benchmarks/regression";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

export type CompareMetricRow = Readonly<{
  label: string;
  base: string;
  head: string;
  delta: string;
  deltaValue: number | null;
  higherIsBetter?: boolean;
}>;

export function buildCompareMetricRows(baseRun: BenchmarkRun, headRun: BenchmarkRun): CompareMetricRow[] {
  const p99Delta = pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms);
  const throughputDelta = pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true);
  const errorRateDelta = pctChange(baseRun.k6.error_rate, headRun.k6.error_rate);
  const overheadDelta = pctChange(
    baseRun.stages.total_overhead_p99_ms,
    headRun.stages.total_overhead_p99_ms,
  );

  return [
    {
      label: "Proxy p99",
      base: formatMs(baseRun.k6.p99_ms),
      head: formatMs(headRun.k6.p99_ms),
      delta: formatDeltaPct(p99Delta),
      deltaValue: p99Delta,
    },
    {
      label: "Throughput",
      base: formatReqPerSec(baseRun.k6.req_per_s),
      head: formatReqPerSec(headRun.k6.req_per_s),
      delta: formatDeltaPct(throughputDelta),
      deltaValue: throughputDelta,
      higherIsBetter: true,
    },
    {
      label: "Error rate",
      base: formatPercent(baseRun.k6.error_rate),
      head: formatPercent(headRun.k6.error_rate),
      delta: formatDeltaPct(errorRateDelta),
      deltaValue: errorRateDelta,
    },
    {
      label: "Total overhead p99",
      base: formatMs(baseRun.stages.total_overhead_p99_ms),
      head: formatMs(headRun.stages.total_overhead_p99_ms),
      delta: formatDeltaPct(overheadDelta),
      deltaValue: overheadDelta,
    },
  ];
}
