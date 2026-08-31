"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { useWritePipelineBenchmarkData } from "@/hooks/use-write-pipeline-benchmark-data";
import { WRITE_PIPELINE_SLA_TARGETS } from "@/lib/benchmarks/constants";
import type { WritePipelineBenchmarkRun } from "@/lib/benchmarks/write-pipeline-schema";

function OverviewKpis({ latest }: { readonly latest: WritePipelineBenchmarkRun }) {
  const m = latest.metrics;
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
      <KpiCard label="p50" value={`${m.latency_ms_p50.toFixed(2)} ms`} />
      <KpiCard label="p95 (SLA ≤ 200 ms)" value={`${m.latency_ms_p95.toFixed(2)} ms`} />
      <KpiCard label="p99" value={`${m.latency_ms_p99.toFixed(2)} ms`} />
    </div>
  );
}

export function BenchmarkWritePipelinePanel() {
  const { latest, isLoading, isError, errorMessage, refresh } = useWritePipelineBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[240px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load write-pipeline benchmark data"}
        onRetry={() => {
          void refresh();
        }}
      />
    );
  }

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  const slaOk = latest.metrics.latency_ms_p95 <= WRITE_PIPELINE_SLA_TARGETS.latency_ms_p95;

  return (
    <div className="space-y-8">
      <p className="font-mono text-sm uppercase text-muted-foreground">
        Status: {latest.status ?? "unknown"} · run #{latest.run_number} · {latest.short_sha}
      </p>
      <OverviewKpis latest={latest} />
      <p className="text-sm text-muted-foreground">
        {latest.iterations != null ? `${latest.iterations} iterations` : "—"}
        {slaOk ? " · p95 within SLA" : " · p95 above SLA"}
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

export function BenchmarkWritePipelineHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useWritePipelineBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load write-pipeline benchmark data"}
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
            <th className="py-2 font-medium">p50</th>
            <th className="py-2 font-medium">p95</th>
            <th className="py-2 font-medium">p99</th>
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
                {run.metrics.latency_ms_p50.toFixed(2)} ms
              </td>
              <td className="py-2 font-mono text-sm tabular-nums">
                {run.metrics.latency_ms_p95.toFixed(2)} ms
              </td>
              <td className="py-2 font-mono text-sm tabular-nums">
                {run.metrics.latency_ms_p99.toFixed(2)} ms
              </td>
              <td className="py-2 font-mono text-xs text-muted-foreground">{run.timestamp}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
