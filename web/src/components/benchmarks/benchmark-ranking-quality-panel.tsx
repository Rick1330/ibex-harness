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
import { useRankingQualityBenchmarkData } from "@/hooks/use-memory-suite-benchmark-data";
import { RANKING_QUALITY_SLA_TARGETS } from "@/lib/benchmarks/constants";
import { formatSuitePct } from "@/lib/benchmarks/format";
import { parseTimeRange } from "@/lib/benchmarks/plot";
import type { RankingQualityBenchmarkRun } from "@/lib/benchmarks/ranking-quality-schema";
import {
  deltaPctVsPrevious,
  filterSuiteRunsByRange,
  suiteRunsToTrendData,
  toRunStatus,
} from "@/lib/benchmarks/suite-trend";

const LOAD_ERROR = "Failed to load ranking-quality benchmark data";
const COMPARE_PATH = "/benchmarks/memory/ranking-quality/compare";

function formatInvertedPct(inverted: number): string {
  return formatSuitePct(1 - inverted);
}

function RankingKpis({
  latest,
  previous,
}: Readonly<{
  latest: RankingQualityBenchmarkRun;
  previous: RankingQualityBenchmarkRun | undefined;
}>) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Precision@5"
        value={formatSuitePct(latest.metrics.precision_at_5)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.precision_at_5,
          previous?.metrics.precision_at_5,
        )}
        higherIsBetter
      />
      <KpiCard
        label="Recall@10"
        value={formatSuitePct(latest.metrics.recall_at_10)}
        deltaPct={deltaPctVsPrevious(
          latest.metrics.recall_at_10,
          previous?.metrics.recall_at_10,
        )}
        higherIsBetter
      />
      <KpiCard
        label="MRR"
        value={formatSuitePct(latest.metrics.mrr)}
        deltaPct={deltaPctVsPrevious(latest.metrics.mrr, previous?.metrics.mrr)}
        higherIsBetter
      />
      <KpiCard
        label="Queries"
        value={latest.query_count != null ? String(latest.query_count) : "—"}
      />
    </div>
  );
}

function RankingSla({ latest }: Readonly<{ latest: RankingQualityBenchmarkRun }>) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Quality floors
      </h2>
      <div className="grid gap-4">
        <SlaGauge
          label="Precision@5 (higher better)"
          value={1 - latest.metrics.precision_at_5}
          target={1 - RANKING_QUALITY_SLA_TARGETS.precision_at_5}
          formatValue={formatInvertedPct}
        />
        <SlaGauge
          label="Recall@10 (higher better)"
          value={1 - latest.metrics.recall_at_10}
          target={1 - RANKING_QUALITY_SLA_TARGETS.recall_at_10}
          formatValue={formatInvertedPct}
        />
        <SlaGauge
          label="MRR (higher better)"
          value={1 - latest.metrics.mrr}
          target={1 - RANKING_QUALITY_SLA_TARGETS.mrr}
          formatValue={formatInvertedPct}
        />
      </div>
    </section>
  );
}

function RankingTrend({
  range,
  filtered,
}: Readonly<{
  range: string;
  filtered: readonly RankingQualityBenchmarkRun[];
}>) {
  return (
    <section className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Precision@5 trend
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <TimeRangePicker />
          <SuiteExportCsvButton
            filename={`ranking-quality-${range}.csv`}
            headers={[
              "run_number",
              "short_sha",
              "status",
              "precision_at_5",
              "recall_at_10",
              "mrr",
              "timestamp",
            ]}
            rows={filtered.map((run) => [
              run.run_number,
              run.short_sha,
              run.status ?? "unknown",
              run.metrics.precision_at_5,
              run.metrics.recall_at_10,
              run.metrics.mrr,
              run.timestamp,
            ])}
          />
        </div>
      </div>
      <SuiteTrendChart
        data={suiteRunsToTrendData(filtered, (run) => run.metrics.precision_at_5)}
        yTickFormat={(value) => `${(value * 100).toFixed(0)}%`}
      />
    </section>
  );
}

function RankingOverviewContent() {
  const { latest, runs, isLoading, isError, errorMessage, refresh } =
    useRankingQualityBenchmarkData();
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
          kpis={<RankingKpis latest={latest} previous={previous} />}
          sla={<RankingSla latest={latest} />}
          trend={<RankingTrend range={range} filtered={filtered} />}
        />
      ) : null}
    </BenchmarkSuitePanelShell>
  );
}

export function BenchmarkRankingQualityPanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[240px]" />}>
      <RankingOverviewContent />
    </Suspense>
  );
}

export function BenchmarkRankingQualityHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useRankingQualityBenchmarkData();

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
        csvFilename="ranking-quality-history.csv"
        columns={[
          { header: "Run #", cell: (run) => run.run_number, csv: (run) => run.run_number },
          {
            header: "SHA",
            cell: (run) => run.short_sha,
            csv: (run) => run.short_sha,
            className: "px-4 py-3 font-mono text-sm",
          },
          {
            header: "Status",
            cell: (run) => (run.status ?? "unknown").toUpperCase(),
            csv: (run) => run.status ?? "unknown",
          },
          {
            header: "Precision@5",
            cell: (run) => formatSuitePct(run.metrics.precision_at_5),
            csv: (run) => run.metrics.precision_at_5,
          },
          {
            header: "Recall@10",
            cell: (run) => formatSuitePct(run.metrics.recall_at_10),
            csv: (run) => run.metrics.recall_at_10,
          },
          {
            header: "MRR",
            cell: (run) => formatSuitePct(run.metrics.mrr),
            csv: (run) => run.metrics.mrr,
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

function rankingCompareRows(
  base: RankingQualityBenchmarkRun,
  head: RankingQualityBenchmarkRun,
) {
  return [
    {
      label: "Precision@5",
      base: formatSuitePct(base.metrics.precision_at_5),
      head: formatSuitePct(head.metrics.precision_at_5),
      delta: formatSuitePct(head.metrics.precision_at_5 - base.metrics.precision_at_5),
      deltaValue: deltaPctVsPrevious(
        head.metrics.precision_at_5,
        base.metrics.precision_at_5,
      ),
      higherIsBetter: true,
    },
    {
      label: "Recall@10",
      base: formatSuitePct(base.metrics.recall_at_10),
      head: formatSuitePct(head.metrics.recall_at_10),
      delta: formatSuitePct(head.metrics.recall_at_10 - base.metrics.recall_at_10),
      deltaValue: deltaPctVsPrevious(head.metrics.recall_at_10, base.metrics.recall_at_10),
      higherIsBetter: true,
    },
    {
      label: "MRR",
      base: formatSuitePct(base.metrics.mrr),
      head: formatSuitePct(head.metrics.mrr),
      delta: formatSuitePct(head.metrics.mrr - base.metrics.mrr),
      deltaValue: deltaPctVsPrevious(head.metrics.mrr, base.metrics.mrr),
      higherIsBetter: true,
    },
  ];
}

export function BenchmarkRankingQualityComparePanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useRankingQualityBenchmarkData();
  return (
    <SuiteComparePanel
      runs={runs}
      isLoading={isLoading}
      isError={isError}
      errorMessage={errorMessage}
      loadErrorLabel={LOAD_ERROR}
      comparePath={COMPARE_PATH}
      buildRows={rankingCompareRows}
      onRetry={() => {
        void refresh();
      }}
    />
  );
}
