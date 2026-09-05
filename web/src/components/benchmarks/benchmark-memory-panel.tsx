"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { SuiteExportCsvButton } from "@/components/benchmarks/suite-export-csv-button";
import { SuiteOverviewLayout } from "@/components/benchmarks/suite-overview-layout";
import { SuiteStatusBadge } from "@/components/benchmarks/suite-status-badge";
import { SuiteTrendChart } from "@/components/benchmarks/suite-trend-chart";
import { TimeRangePicker } from "@/components/benchmarks/time-range-picker";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { BenchmarkWorkflowRunLink } from "@/components/benchmarks/benchmark-workflow-run-link";
import { HNSW_SLA_TARGETS } from "@/lib/benchmarks/constants";
import {
  corpusSizeLabel,
  formatRecallPct,
  largestCorpusResult,
} from "@/lib/benchmarks/hnsw-runs";
import type { HnswBenchmarkRun, HnswSizeResult } from "@/lib/benchmarks/hnsw-schema";
import { parseTimeRange } from "@/lib/benchmarks/plot";
import {
  deltaPctVsPrevious,
  filterSuiteRunsByRange,
  suiteRunsToTrendData,
  toRunStatus,
} from "@/lib/benchmarks/suite-trend";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

function ResultRow({ result }: Readonly<{ result: HnswSizeResult }>) {
  return (
    <tr className="border-b border-border/60">
      <td className="py-2 font-mono text-sm">{corpusSizeLabel(result.corpus_size)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.query_count}</td>
      <td className="py-2 font-mono text-sm tabular-nums">
        {formatRecallPct(result.recall_at_10)}
      </td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p50.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p95.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.latency_ms_p99.toFixed(2)}</td>
      <td className="py-2 font-mono text-sm tabular-nums">{result.ef_search}</td>
    </tr>
  );
}

function SlaSection({
  worstRecall,
  at1m,
}: {
  readonly worstRecall: number;
  readonly at1m: HnswSizeResult | undefined;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Track B / Track E SLAs
      </h2>
      <div className="grid gap-4">
        <SlaGauge
          label="Worst recall@10 (target ≥ 98%)"
          value={1 - worstRecall}
          target={1 - HNSW_SLA_TARGETS.recall_at_10}
          formatValue={(value) => formatRecallPct(1 - value)}
        />
        {at1m ? (
          <>
            <SlaGauge
              label="1M search p95"
              value={at1m.latency_ms_p95}
              target={HNSW_SLA_TARGETS.p95_ms_1m}
            />
            <SlaGauge
              label="1M search p99"
              value={at1m.latency_ms_p99}
              target={HNSW_SLA_TARGETS.p99_ms_1m}
            />
          </>
        ) : null}
      </div>
    </section>
  );
}

function ResultsTable({ latest }: { readonly latest: HnswBenchmarkRun }) {
  return (
    <section className="space-y-3">
      <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
        Per-size results
      </h2>
      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-max min-w-full text-left">
          <thead>
            <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-4 py-2 font-medium">Corpus</th>
              <th className="px-4 py-2 font-medium">Queries</th>
              <th className="px-4 py-2 font-medium">Recall@10</th>
              <th className="px-4 py-2 font-medium">p50 ms</th>
              <th className="px-4 py-2 font-medium">p95 ms</th>
              <th className="px-4 py-2 font-medium">p99 ms</th>
              <th className="px-4 py-2 font-medium">ef</th>
            </tr>
          </thead>
          <tbody>
            {latest.results.map((result) => (
              <ResultRow
                key={`${result.corpus_size}-${result.ef_search}-${result.min_similarity ?? 0}`}
                result={result}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MemoryOverviewContent() {
  const { latest, runs, isLoading, isError, errorMessage, refresh } = useHnswBenchmarkData();
  const searchParams = useSearchParams();
  const range = parseTimeRange(searchParams.get("range"));
  const filtered = filterSuiteRunsByRange(runs, range);
  const previous = runs[1];

  if (isLoading) {
    return <ChartSkeleton className="h-[240px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load HNSW data"}
        onRetry={() => {
          void refresh();
        }}
      />
    );
  }

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  const at1m = latest.results.find((r) => r.corpus_size >= 1_000_000);
  const worstRecall = Math.min(...latest.results.map((r) => r.recall_at_10));

  return (
    <SuiteOverviewLayout
      status={
        <SuiteStatusBadge
          status={toRunStatus(latest.status)}
          runNumber={latest.run_number}
          shortSha={latest.short_sha}
          branch={latest.branch}
          timestamp={latest.timestamp}
          detail={
            <span className="flex flex-wrap gap-3">
              <Link href="/benchmarks/memory/latency" className="underline underline-offset-2">
                Latency detail
              </Link>
              <Link href="/benchmarks/memory/history" className="underline underline-offset-2">
                History
              </Link>
              <Link href="/benchmarks/memory/compare" className="underline underline-offset-2">
                Compare
              </Link>
              <BenchmarkWorkflowRunLink runUrl={latest.run_url} />
            </span>
          }
        />
      }
      kpis={
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <KpiCard
            label="Mean recall@10"
            value={formatRecallPct(latest.mean_recall_at_10)}
            deltaPct={deltaPctVsPrevious(
              latest.mean_recall_at_10,
              previous?.mean_recall_at_10,
            )}
            higherIsBetter
          />
          <KpiCard
            label="Sizes measured"
            value={latest.results.map((r) => corpusSizeLabel(r.corpus_size)).join(" · ")}
          />
          <KpiCard label="Latest short SHA" value={latest.short_sha} hint={latest.branch} />
          <KpiCard label="Run #" value={String(latest.run_number)} hint={latest.timestamp} />
        </div>
      }
      sla={<SlaSection worstRecall={worstRecall} at1m={at1m} />}
      trend={
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Mean recall@10 trend
            </h2>
            <div className="flex flex-wrap items-center gap-2">
              <TimeRangePicker />
              <SuiteExportCsvButton
                filename={`hnsw-overview-${range}.csv`}
                headers={["run_number", "short_sha", "status", "mean_recall_at_10", "timestamp"]}
                rows={filtered.map((run) => [
                  run.run_number,
                  run.short_sha,
                  run.status ?? "unknown",
                  run.mean_recall_at_10,
                  run.timestamp,
                ])}
              />
            </div>
          </div>
          <SuiteTrendChart
            data={suiteRunsToTrendData(filtered, (run) => run.mean_recall_at_10)}
            yTickFormat={(value) => `${(value * 100).toFixed(0)}%`}
          />
        </section>
      }
      extras={<ResultsTable latest={latest} />}
    />
  );
}

export function BenchmarkMemoryPanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[240px]" />}>
      <MemoryOverviewContent />
    </Suspense>
  );
}

export function MemorySuiteSummaryCard() {
  const { latest, isLoading, isError } = useHnswBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[120px]" />;
  }

  if (isError || !latest) {
    return (
      <div className="rounded-md border border-border p-4 text-sm text-muted-foreground">
        <p className="font-medium text-foreground">Memory HNSW</p>
        <p className="mt-1">No published HNSW runs yet.</p>
        <Link href="/benchmarks/memory" className="mt-2 inline-block underline underline-offset-2">
          Open Memory suite
        </Link>
      </div>
    );
  }

  const largest = largestCorpusResult(latest);

  return (
    <div className="rounded-md border border-border p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Memory HNSW
        </h2>
        <Link
          href="/benchmarks/memory"
          className="text-sm text-muted-foreground underline-offset-2 hover:underline"
        >
          Open suite
        </Link>
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-3">
        <KpiCard
          label="Mean recall@10"
          value={formatRecallPct(latest.mean_recall_at_10)}
          higherIsBetter
        />
        <KpiCard
          label={largest ? `${corpusSizeLabel(largest.corpus_size)} p95` : "Largest p95"}
          value={largest ? `${largest.latency_ms_p95.toFixed(1)} ms` : "—"}
        />
        <KpiCard label="Latest" value={latest.short_sha} hint={latest.branch} />
      </div>
    </div>
  );
}
