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
  return [
    {
      label: "Proxy p99",
      base: formatMs(baseRun.k6.p99_ms),
      head: formatMs(headRun.k6.p99_ms),
      delta: formatDeltaPct(pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms)),
      deltaValue: pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms),
    },
    {
      label: "Throughput",
      base: formatReqPerSec(baseRun.k6.req_per_s),
      head: formatReqPerSec(headRun.k6.req_per_s),
      delta: formatDeltaPct(pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true)),
      deltaValue: pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true),
      higherIsBetter: true,
    },
    {
      label: "Error rate",
      base: formatPercent(baseRun.k6.error_rate),
      head: formatPercent(headRun.k6.error_rate),
      delta: formatDeltaPct(pctChange(baseRun.k6.error_rate, headRun.k6.error_rate)),
      deltaValue: pctChange(baseRun.k6.error_rate, headRun.k6.error_rate),
    },
    {
      label: "Total overhead p99",
      base: formatMs(baseRun.stages.total_overhead_p99_ms),
      head: formatMs(headRun.stages.total_overhead_p99_ms),
      delta: formatDeltaPct(
        pctChange(baseRun.stages.total_overhead_p99_ms, headRun.stages.total_overhead_p99_ms),
      ),
      deltaValue: pctChange(baseRun.stages.total_overhead_p99_ms, headRun.stages.total_overhead_p99_ms),
    },
  ];
}
