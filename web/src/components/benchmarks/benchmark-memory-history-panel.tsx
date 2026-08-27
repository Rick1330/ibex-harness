"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import {
  corpusSizeLabel,
  formatRecallPct,
  largestCorpusResult,
} from "@/lib/benchmarks/hnsw-runs";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

export function BenchmarkMemoryHistoryPanel() {
  const { runs, isLoading, isError, errorMessage, refresh } = useHnswBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load HNSW benchmark data"}
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
            <th className="py-2 font-medium">Branch</th>
            <th className="py-2 font-medium">Status</th>
            <th className="py-2 font-medium">Mean recall</th>
            <th className="py-2 font-medium">Largest p95</th>
            <th className="py-2 font-medium">Sizes</th>
            <th className="py-2 font-medium">When</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const largest = largestCorpusResult(run);
            return (
              <tr key={run.run_number} className="border-b border-border/60">
                <td className="py-2 font-mono text-sm tabular-nums">
                  <Link
                    href={`/benchmarks/memory/history/${run.run_number}`}
                    className="underline-offset-2 hover:underline"
                  >
                    {run.run_number}
                  </Link>
                </td>
                <td className="py-2 font-mono text-sm">{run.short_sha}</td>
                <td className="py-2 font-mono text-sm">{run.branch}</td>
                <td className="py-2 font-mono text-sm uppercase">{run.status ?? "unknown"}</td>
                <td className="py-2 font-mono text-sm tabular-nums">
                  {formatRecallPct(run.mean_recall_at_10)}
                </td>
                <td className="py-2 font-mono text-sm tabular-nums">
                  {largest ? `${largest.latency_ms_p95.toFixed(2)} ms` : "—"}
                </td>
                <td className="py-2 font-mono text-sm">
                  {run.results.map((r) => corpusSizeLabel(r.corpus_size)).join(" · ")}
                </td>
                <td className="py-2 font-mono text-xs text-muted-foreground">{run.timestamp}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
