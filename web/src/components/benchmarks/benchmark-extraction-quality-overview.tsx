"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { KpiCard } from "@/components/benchmarks/kpi-card";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { SuiteExportCsvButton } from "@/components/benchmarks/suite-export-csv-button";
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

function ExtractionStatus({
  latest,
}: Readonly<{ latest: ExtractionQualityBenchmarkRun }>) {
  return (
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
  );
}

function ExtractionOverviewContent() {
  const { latest, runs, isLoading, isError, errorMessage, refresh } =
    useExtractionQualityBenchmarkData();
  const searchParams = useSearchParams();
  const range = parseTimeRange(searchParams.get("range"));
  const filtered = filterSuiteRunsByRange(runs, range);

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
          status={<ExtractionStatus latest={latest} />}
          kpis={<ExtractionKpis latest={latest} previous={runs[1]} />}
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
