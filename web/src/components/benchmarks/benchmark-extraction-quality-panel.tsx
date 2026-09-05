"use client";

import { SuiteComparePanel } from "@/components/benchmarks/suite-compare-panel";
import { SuiteHistoryTable } from "@/components/benchmarks/suite-history-table";
import { BenchmarkSuitePanelShell } from "@/components/benchmarks/benchmark-suite-panel-shell";
import { useExtractionQualityBenchmarkData } from "@/hooks/use-memory-suite-benchmark-data";
import type { ExtractionQualityBenchmarkRun } from "@/lib/benchmarks/extraction-quality-schema";
import { formatSuitePct } from "@/lib/benchmarks/format";
import { deltaPctVsPrevious } from "@/lib/benchmarks/suite-trend";

export { BenchmarkExtractionQualityPanel } from "@/components/benchmarks/benchmark-extraction-quality-overview";

const LOAD_ERROR = "Failed to load extraction-quality benchmark data";
const COMPARE_PATH = "/benchmarks/extraction-quality/compare";

export function BenchmarkExtractionQualityHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } =
    useExtractionQualityBenchmarkData();

  return (
    <BenchmarkSuitePanelShell
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      isEmpty={runs.length === 0}
      emptyTitle="No extraction-quality history yet"
      emptyMessage="No published runs to list. History will appear here after the extraction-quality eval publishes JSON to main."
      skeletonClassName="h-[200px]"
      onRetry={() => {
        void refresh();
      }}
    >
      <SuiteHistoryTable
        rows={runs}
        rowKey={(run) => run.run_number}
        getStatus={(run) => run.status ?? "unknown"}
        getBranch={(run) => run.branch}
        csvFilename="extraction-quality-history.csv"
        columns={[
          { header: "Run #", cell: (run) => run.run_number, csv: (run) => run.run_number },
          { header: "SHA", cell: (run) => run.short_sha, csv: (run) => run.short_sha },
          {
            header: "Status",
            cell: (run) => (run.status ?? "unknown").toUpperCase(),
            csv: (run) => run.status ?? "unknown",
          },
          {
            header: "Precision macro",
            cell: (run) => formatSuitePct(run.metrics.precision_macro),
            csv: (run) => run.metrics.precision_macro,
          },
          {
            header: "Recall macro",
            cell: (run) => formatSuitePct(run.metrics.recall_macro),
            csv: (run) => run.metrics.recall_macro,
          },
          {
            header: "Category",
            cell: (run) => formatSuitePct(run.metrics.category_assignment_accuracy),
            csv: (run) => run.metrics.category_assignment_accuracy,
          },
          {
            header: "Temporal",
            cell: (run) => formatSuitePct(run.metrics.temporal_field_accuracy),
            csv: (run) => run.metrics.temporal_field_accuracy,
          },
          {
            header: "When",
            cell: (run) => run.timestamp,
            csv: (run) => run.timestamp,
            className: "px-4 py-3 font-mono text-xs text-muted-foreground",
          },
        ]}
      />
    </BenchmarkSuitePanelShell>
  );
}

function extractionCompareRows(
  base: ExtractionQualityBenchmarkRun,
  head: ExtractionQualityBenchmarkRun,
) {
  return [
    {
      label: "precision_macro",
      base: formatSuitePct(base.metrics.precision_macro),
      head: formatSuitePct(head.metrics.precision_macro),
      delta: formatSuitePct(head.metrics.precision_macro - base.metrics.precision_macro),
      deltaValue: deltaPctVsPrevious(
        head.metrics.precision_macro,
        base.metrics.precision_macro,
      ),
      higherIsBetter: true,
    },
    {
      label: "recall_macro",
      base: formatSuitePct(base.metrics.recall_macro),
      head: formatSuitePct(head.metrics.recall_macro),
      delta: formatSuitePct(head.metrics.recall_macro - base.metrics.recall_macro),
      deltaValue: deltaPctVsPrevious(head.metrics.recall_macro, base.metrics.recall_macro),
      higherIsBetter: true,
    },
    {
      label: "category_assignment_accuracy",
      base: formatSuitePct(base.metrics.category_assignment_accuracy),
      head: formatSuitePct(head.metrics.category_assignment_accuracy),
      delta: formatSuitePct(
        head.metrics.category_assignment_accuracy - base.metrics.category_assignment_accuracy,
      ),
      deltaValue: deltaPctVsPrevious(
        head.metrics.category_assignment_accuracy,
        base.metrics.category_assignment_accuracy,
      ),
      higherIsBetter: true,
    },
    {
      label: "temporal_field_accuracy",
      base: formatSuitePct(base.metrics.temporal_field_accuracy),
      head: formatSuitePct(head.metrics.temporal_field_accuracy),
      delta: formatSuitePct(
        head.metrics.temporal_field_accuracy - base.metrics.temporal_field_accuracy,
      ),
      deltaValue: deltaPctVsPrevious(
        head.metrics.temporal_field_accuracy,
        base.metrics.temporal_field_accuracy,
      ),
      higherIsBetter: true,
    },
  ];
}

export function BenchmarkExtractionQualityComparePanel() {
  const { runs, isLoading, isError, errorMessage, refresh } =
    useExtractionQualityBenchmarkData();
  return (
    <SuiteComparePanel
      runs={runs}
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      comparePath={COMPARE_PATH}
      buildRows={extractionCompareRows}
      emptyTitle="No extraction-quality runs to compare"
      emptyMessage="Compare needs at least two published runs. None are in the public JSON yet."
      onRetry={() => {
        void refresh();
      }}
    />
  );
}
