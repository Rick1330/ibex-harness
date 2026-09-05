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
import { useWritePipelineBenchmarkData } from "@/hooks/use-memory-suite-benchmark-data";
import { WRITE_PIPELINE_SLA_TARGETS } from "@/lib/benchmarks/constants";
import { formatMs } from "@/lib/benchmarks/format";
import { parseTimeRange } from "@/lib/benchmarks/plot";
import {
  deltaPctVsPrevious,
  filterSuiteRunsByRange,
  suiteRunsToTrendData,
  toRunStatus,
} from "@/lib/benchmarks/suite-trend";
import type { WritePipelineBenchmarkRun } from "@/lib/benchmarks/write-pipeline-schema";

const LOAD_ERROR = "Failed to load write-pipeline benchmark data";
const COMPARE_PATH = "/benchmarks/memory/write-pipeline/compare";

function WriteKpis({
  latest,
  previous,
}: Readonly<{
  latest: WritePipelineBenchmarkRun;
  previous: WritePipelineBenchmarkRun | undefined;
}>) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <KpiCard
        label="p50"
        value={formatMs(latest.metrics.latency_ms_p50)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.latency_ms_p50,
          previous?.metrics.latency_ms_p50,
        )}
      />
      <KpiCard
        label="p95"
        value={formatMs(latest.metrics.latency_ms_p95)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.latency_ms_p95,
          previous?.metrics.latency_ms_p95,
        )}
      />
      <KpiCard
        label="p99"
        value={formatMs(latest.metrics.latency_ms_p99)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.latency_ms_p99,
          previous?.metrics.latency_ms_p99,
        )}
      />
    </div>
  );
}

function WriteTrend({
  range,
  filtered,
}: Readonly<{
  range: string;
  filtered: readonly WritePipelineBenchmarkRun[];
}>) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Write p95 trend
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <TimeRangePicker />
          <SuiteExportCsvButton
            filename={`write-pipeline-${range}.csv`}
            headers={["run_number", "short_sha", "status", "p50", "p95", "p99", "timestamp"]}
            rows={filtered.map((run) => [
              run.run_number,
              run.short_sha,
              run.status ?? "unknown",
              run.metrics.latency_ms_p50,
              run.metrics.latency_ms_p95,
              run.metrics.latency_ms_p99,
              run.timestamp,
            ])}
          />
        </div>
      </div>
      <SuiteTrendChart
        data={suiteRunsToTrendData(filtered, (run) => run.metrics.latency_ms_p95)}
        targetMs={WRITE_PIPELINE_SLA_TARGETS.latency_ms_p95}
        yTickFormat={(value) => `${value.toFixed(1)} ms`}
      />
    </section>
  );
}

function WriteOverviewContent() {
  const { latest, runs, isLoading, isError, errorMessage, refresh } =
    useWritePipelineBenchmarkData();
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
                <BenchmarkWorkflowRunLink runUrl={latest.run_url} label="Open workflow run" />
              }
            />
          }
          kpis={<WriteKpis latest={latest} previous={previous} />}
          sla={
            <section className="space-y-3">
              <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
                SLA
              </h2>
              <SlaGauge
                label="Write p95"
                value={latest.metrics.latency_ms_p95}
                target={WRITE_PIPELINE_SLA_TARGETS.latency_ms_p95}
              />
            </section>
          }
          trend={<WriteTrend range={range} filtered={filtered} />}
        />
      ) : null}
    </BenchmarkSuitePanelShell>
  );
}

export function BenchmarkWritePipelinePanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[240px]" />}>
      <WriteOverviewContent />
    </Suspense>
  );
}

export function BenchmarkWritePipelineHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useWritePipelineBenchmarkData();

  return (
    <BenchmarkSuitePanelShell
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      isEmpty={runs.length === 0}
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
        csvFilename="write-pipeline-history.csv"
        columns={[
          { header: "Run #", cell: (run) => run.run_number, csv: (run) => run.run_number },
          { header: "SHA", cell: (run) => run.short_sha, csv: (run) => run.short_sha },
          {
            header: "Status",
            cell: (run) => (run.status ?? "unknown").toUpperCase(),
            csv: (run) => run.status ?? "unknown",
          },
          {
            header: "p50",
            cell: (run) => formatMs(run.metrics.latency_ms_p50),
            csv: (run) => run.metrics.latency_ms_p50,
          },
          {
            header: "p95",
            cell: (run) => formatMs(run.metrics.latency_ms_p95),
            csv: (run) => run.metrics.latency_ms_p95,
          },
          {
            header: "p99",
            cell: (run) => formatMs(run.metrics.latency_ms_p99),
            csv: (run) => run.metrics.latency_ms_p99,
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

function writeCompareRows(base: WritePipelineBenchmarkRun, head: WritePipelineBenchmarkRun) {
  const p50 = {
    label: "P50",
    base: formatMs(base.metrics.latency_ms_p50),
    head: formatMs(head.metrics.latency_ms_p50),
    delta: formatMs(head.metrics.latency_ms_p50 - base.metrics.latency_ms_p50),
    deltaValue: deltaPctVsPrevious(head.metrics.latency_ms_p50, base.metrics.latency_ms_p50),
    higherIsBetter: false,
  };
  const p95 = {
    label: "P95",
    base: formatMs(base.metrics.latency_ms_p95),
    head: formatMs(head.metrics.latency_ms_p95),
    delta: formatMs(head.metrics.latency_ms_p95 - base.metrics.latency_ms_p95),
    deltaValue: deltaPctVsPrevious(head.metrics.latency_ms_p95, base.metrics.latency_ms_p95),
    higherIsBetter: false,
  };
  const p99 = {
    label: "P99",
    base: formatMs(base.metrics.latency_ms_p99),
    head: formatMs(head.metrics.latency_ms_p99),
    delta: formatMs(head.metrics.latency_ms_p99 - base.metrics.latency_ms_p99),
    deltaValue: deltaPctVsPrevious(head.metrics.latency_ms_p99, base.metrics.latency_ms_p99),
    higherIsBetter: false,
  };
  return [p50, p95, p99];
}

export function BenchmarkWritePipelineComparePanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useWritePipelineBenchmarkData();
  return (
    <SuiteComparePanel
      runs={runs}
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      comparePath={COMPARE_PATH}
      buildRows={writeCompareRows}
      onRetry={() => {
        void refresh();
      }}
    />
  );
}
