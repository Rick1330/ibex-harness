"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { useRankingQualityBenchmarkData } from "@/hooks/use-ranking-quality-benchmark-data";
import type { RankingQualityBenchmarkRun } from "@/lib/benchmarks/ranking-quality-schema";

function formatPct(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function OverviewKpis({ latest }: { readonly latest: RankingQualityBenchmarkRun }) {
  const m = latest.metrics;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard label="Precision@5" value={formatPct(m.precision_at_5)} />
      <KpiCard label="Recall@10" value={formatPct(m.recall_at_10)} />
      <KpiCard label="MRR" value={formatPct(m.mrr)} />
      <KpiCard
        label="Queries"
        value={latest.query_count != null ? String(latest.query_count) : "—"}
      />
    </div>
  );
}

export function BenchmarkRankingQualityPanel() {
  const { latest, isLoading, isError, errorMessage, refresh } = useRankingQualityBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[240px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load ranking-quality benchmark data"}
        onRetry={() => {
          void refresh();
        }}
      />
    );
  }

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="space-y-8">
      <p className="font-mono text-sm uppercase text-muted-foreground">
        Status: {latest.status ?? "unknown"} · run #{latest.run_number} · {latest.short_sha}
      </p>
      <OverviewKpis latest={latest} />
      <p className="text-sm text-muted-foreground">
        Gold set {latest.gold_set ?? "v1"}
        {latest.memory_count != null ? ` · ${latest.memory_count} memories` : ""}
        {latest.run_url ? (
          <>
            {" "}
            ·{" "}
            <a className="underline underline-offset-2" href={latest.run_url}>
              workflow run
            </a>
          </>
        ) : null}
      </p>
    </div>
  );
}

export function BenchmarkRankingQualityHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useRankingQualityBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load ranking-quality benchmark data"}
        onRetry={() => {
          void refresh();
        }}
      />
    );
  }

  if (runs.length === 0) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-left">
        <thead>
          <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
            <th className="py-2 font-medium">Run #</th>
            <th className="py-2 font-medium">SHA</th>
            <th className="py-2 font-medium">Status</th>
            <th className="py-2 font-medium">Precision@5</th>
            <th className="py-2 font-medium">Recall@10</th>
            <th className="py-2 font-medium">MRR</th>
            <th className="py-2 font-medium">When</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.run_number} className="border-b border-border/60">
              <td className="py-2 font-mono text-sm tabular-nums">{run.run_number}</td>
              <td className="py-2 font-mono text-sm">{run.short_sha}</td>
              <td className="py-2 font-mono text-sm uppercase">{run.status ?? "unknown"}</td>
              <td className="py-2 font-mono text-sm tabular-nums">
                {formatPct(run.metrics.precision_at_5)}
              </td>
              <td className="py-2 font-mono text-sm tabular-nums">
                {formatPct(run.metrics.recall_at_10)}
              </td>
              <td className="py-2 font-mono text-sm tabular-nums">{formatPct(run.metrics.mrr)}</td>
              <td className="py-2 font-mono text-xs text-muted-foreground">{run.timestamp}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
