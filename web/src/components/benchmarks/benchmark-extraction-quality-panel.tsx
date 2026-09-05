"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { KpiCard } from "@/components/benchmarks/kpi-card";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { SuiteComparePanel } from "@/components/benchmarks/suite-compare-panel";
import { SuiteExportCsvButton } from "@/components/benchmarks/suite-export-csv-button";
import { SuiteHistoryTable } from "@/components/benchmarks/suite-history-table";
import { SuiteOverviewLayout } from "@/components/benchmarks/suite-overview-layout";
import { SuiteStatusBadge } from "@/components/benchmarks/suite-status-badge";
import { SuiteTrendChart } from "@/components/benchmarks/suite-trend-chart";
import { TimeRangePicker } from "@/components/benchmarks/time-range-picker";
import { BenchmarkSuitePanelShell } from "@/components/benchmarks/benchmark-suite-panel-shell";
import { BenchmarkWorkflowRunLink } from "@/components/benchmarks/benchmark-workflow-run-link";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { useExtractionQualityBenchmarkData } from "@/hooks/use-memory-suite-benchmark-data";
import { EXTRACTION_QUALITY_SLA_TARGETS } from "@/lib/benchmarks/constants";
import type { ExtractionQualityBenchmarkRun } from "@/lib/benchmarks/extraction-quality-schema";
import { formatSuitePct } from "@/lib/benchmarks/format";
import { parseTimeRange } from "@/lib/benchmarks/plot";
import {
  deltaPctVsPrevious,
  filterSuiteRunsByRange,
  suiteRunsToTrendData,
  toRunStatus,
} from "@/lib/benchmarks/suite-trend";

const LOAD_ERROR = "Failed to load extraction-quality benchmark data";
const COMPARE_PATH = "/benchmarks/extraction-quality/compare";

function formatInvertedPct(inverted: number): string {
  return formatSuitePct(1 - inverted);
}

function ExtractionKpis({
  latest,
  previous,
}: Readonly<{
  latest: ExtractionQualityBenchmarkRun;
  previous: ExtractionQualityBenchmarkRun | undefined;
}>) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Precision macro"
        value={formatSuitePct(latest.metrics.precision_macro)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.precision_macro,
          previous?.metrics.precision_macro,
        )}
        higherIsBetter
      />
      <KpiCard
        label="Recall macro"
        value={formatSuitePct(latest.metrics.recall_macro)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.recall_macro,
          previous?.metrics.recall_macro,
        )}
        higherIsBetter
      />
      <KpiCard
        label="Category assignment"
        value={formatSuitePct(latest.metrics.category_assignment_accuracy)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.category_assignment_accuracy,
          previous?.metrics.category_assignment_accuracy,
        )}
        higherIsBetter
      />
      <KpiCard
        label="Temporal fields"
        value={formatSuitePct(latest.metrics.temporal_field_accuracy)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.temporal_field_accuracy,
          previous?.metrics.temporal_field_accuracy,
        )}
        higherIsBetter
      />
    </div>
  );
}

function ExtractionSla({
  latest,
}: Readonly<{ latest: ExtractionQualityBenchmarkRun }>) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Quality floors
      </h2>
      <div className="grid gap-4">
        <SlaGauge
          label="Precision macro"
          value={1 - latest.metrics.precision_macro}
          target={1 - EXTRACTION_QUALITY_SLA_TARGETS.precision_macro}
          formatValue={formatInvertedPct}
        />
        <SlaGauge
          label="Recall macro"
          value={1 - latest.metrics.recall_macro}
          target={1 - EXTRACTION_QUALITY_SLA_TARGETS.recall_macro}
          formatValue={formatInvertedPct}
        />
        <SlaGauge
          label="Category assignment"
          value={1 - latest.metrics.category_assignment_accuracy}
          target={1 - EXTRACTION_QUALITY_SLA_TARGETS.category_assignment_accuracy}
          formatValue={formatInvertedPct}
        />
        <SlaGauge
          label="Temporal fields"
          value={1 - latest.metrics.temporal_field_accuracy}
          target={1 - EXTRACTION_QUALITY_SLA_TARGETS.temporal_field_accuracy}
          formatValue={formatInvertedPct}
        />
      </div>
    </section>
  );
}

function ExtractionTrend({
  range,
  filtered,
}: Readonly<{
  range: string;
  filtered: readonly ExtractionQualityBenchmarkRun[];
}>) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Precision macro trend
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <TimeRangePicker />
          <SuiteExportCsvButton
            filename={`extraction-quality-${range}.csv`}
            headers={[
              "run_number",
              "short_sha",
              "status",
              "precision_macro",
              "recall_macro",
              "timestamp",
            ]}
            rows={filtered.map((run) => [
              run.run_number,
              run.short_sha,
              run.status ?? "unknown",
              run.metrics.precision_macro,
              run.metrics.recall_macro,
              run.timestamp,
            ])}
          />
        </div>
      </div>
      <SuiteTrendChart
        data={suiteRunsToTrendData(filtered, (run) => run.metrics.precision_macro)}
        yTickFormat={(value) => `${(value * 100).toFixed(0)}%`}
      />
    </section>
  );
}

function ExtractionOverviewContent() {
  const { latest, runs, isLoading, isError, errorMessage, refresh } =
    useExtractionQualityBenchmarkData();
  const searchParams = useSearchParams();
  const range = parseTimeRange(searchParams.get("range"));
  const filtered = filterSuiteRunsByRange(runs, range);
  const previous = runs[1];

  return (
    <BenchmarkSuitePanelShell
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      isEmpty={!latest}
      emptyTitle="No extraction-quality runs yet"
      emptyMessage="Published history is empty (runs: []). Cassette/smoke CI will fill this suite once the extraction eval publishes to main — Overview, History, and Compare stay available in the sidebar."
      onRetry={() => {
        void refresh();
      }}
    >
      {latest ? (
        <SuiteOverviewLayout
          status={
            <SuiteStatusBadge
              status={toRunStatus(latest.status)}
              runNumber={latest.run_number}
              shortSha={latest.short_sha}
              branch={latest.branch}
              timestamp={latest.timestamp}
              detail={
                <>
                  Enforcement {latest.enforcement ?? "ci"}
                  {latest.provider ? ` · ${latest.provider}` : ""}
                  {" · "}
                  <BenchmarkWorkflowRunLink runUrl={latest.run_url} label="Open workflow run" />
                </>
              }
            />
          }
          kpis={<ExtractionKpis latest={latest} previous={previous} />}
          sla={<ExtractionSla latest={latest} />}
          trend={<ExtractionTrend range={range} filtered={filtered} />}
        />
      ) : null}
    </BenchmarkSuitePanelShell>
  );
}

export function BenchmarkExtractionQualityPanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[240px]" />}>
      <ExtractionOverviewContent />
    </Suspense>
  );
}

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
