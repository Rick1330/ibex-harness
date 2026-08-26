import type { CompareMetricRow } from "@/lib/benchmarks/compare-metrics";
import { formatDeltaPct, formatMs } from "@/lib/benchmarks/format";
import {
  corpusSizeLabel,
  formatRecallPct,
  uniqueCorpusSizes,
} from "@/lib/benchmarks/hnsw-runs";
import type { HnswBenchmarkRun } from "@/lib/benchmarks/hnsw-schema";
import { pctChange } from "@/lib/benchmarks/regression";

export function buildHnswCompareMetricRows(
  baseRun: HnswBenchmarkRun,
  headRun: HnswBenchmarkRun,
): CompareMetricRow[] {
  const rows: CompareMetricRow[] = [];

  const meanDelta = pctChange(baseRun.mean_recall_at_10, headRun.mean_recall_at_10, true);
  rows.push({
    label: "Mean recall@10",
    base: formatRecallPct(baseRun.mean_recall_at_10),
    head: formatRecallPct(headRun.mean_recall_at_10),
    delta: formatDeltaPct(meanDelta),
    deltaValue: meanDelta,
    higherIsBetter: true,
  });

  for (const size of uniqueCorpusSizes([baseRun, headRun])) {
    const baseCell = baseRun.results.find((r) => r.corpus_size === size);
    const headCell = headRun.results.find((r) => r.corpus_size === size);
    if (!baseCell || !headCell) continue;

    const label = corpusSizeLabel(size);
    const recallDelta = pctChange(baseCell.recall_at_10, headCell.recall_at_10, true);
    rows.push({
      label: `${label} recall@10`,
      base: formatRecallPct(baseCell.recall_at_10),
      head: formatRecallPct(headCell.recall_at_10),
      delta: formatDeltaPct(recallDelta),
      deltaValue: recallDelta,
      higherIsBetter: true,
    });
    const p95Delta = pctChange(baseCell.latency_ms_p95, headCell.latency_ms_p95);
    rows.push({
      label: `${label} p95`,
      base: formatMs(baseCell.latency_ms_p95),
      head: formatMs(headCell.latency_ms_p95),
      delta: formatDeltaPct(p95Delta),
      deltaValue: p95Delta,
    });
    const p99Delta = pctChange(baseCell.latency_ms_p99, headCell.latency_ms_p99);
    rows.push({
      label: `${label} p99`,
      base: formatMs(baseCell.latency_ms_p99),
      head: formatMs(headCell.latency_ms_p99),
      delta: formatDeltaPct(p99Delta),
      deltaValue: p99Delta,
    });
  }

  return rows;
}
