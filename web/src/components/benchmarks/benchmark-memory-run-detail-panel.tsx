"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import {
  corpusSizeLabel,
  findHnswRunBySha,
  formatRecallPct,
} from "@/lib/benchmarks/hnsw-runs";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

type BenchmarkMemoryRunDetailPanelProps = Readonly<{
  sha: string;
}>;

export function BenchmarkMemoryRunDetailPanel({ sha }: BenchmarkMemoryRunDetailPanelProps) {
  const { runs, isLoading, isError, errorMessage } = useHnswBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState message={errorMessage ?? "Failed to load HNSW benchmark data"} />
    );
  }

  const run = findHnswRunBySha(runs, sha);
  if (!run) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap gap-3 text-sm">
        <Link href="/benchmarks/memory/history" className="underline underline-offset-2">
          ← History
        </Link>
        <Link
          href={`/benchmarks/memory/compare?head=${run.short_sha}`}
          className="underline underline-offset-2"
        >
          Compare
        </Link>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="SHA" value={run.short_sha} hint={run.sha} />
        <KpiCard label="Branch" value={run.branch} />
        <KpiCard
          label="Mean recall@10"
          value={formatRecallPct(run.mean_recall_at_10)}
          higherIsBetter
        />
        <KpiCard label="Status" value={(run.status ?? "pass").toUpperCase()} />
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold tracking-tight">Cells</h2>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left">
            <thead>
              <tr className="border-b border-border text-xs uppercase tracking-wide text-muted-foreground">
                <th className="py-2 font-medium">Corpus</th>
                <th className="py-2 font-medium">Recall@10</th>
                <th className="py-2 font-medium">p95</th>
                <th className="py-2 font-medium">p99</th>
                <th className="py-2 font-medium">ef</th>
                <th className="py-2 font-medium">min_sim</th>
                <th className="py-2 font-medium">build</th>
              </tr>
            </thead>
            <tbody>
              {run.results.map((result) => (
                <tr
                  key={`${result.corpus_size}-${result.ef_search}`}
                  className="border-b border-border/60"
                >
                  <td className="py-2 font-mono text-sm">
                    {corpusSizeLabel(result.corpus_size)}
                  </td>
                  <td className="py-2 font-mono text-sm tabular-nums">
                    {formatRecallPct(result.recall_at_10)}
                  </td>
                  <td className="py-2 font-mono text-sm tabular-nums">
                    {result.latency_ms_p95.toFixed(2)}
                  </td>
                  <td className="py-2 font-mono text-sm tabular-nums">
                    {result.latency_ms_p99.toFixed(2)}
                  </td>
                  <td className="py-2 font-mono text-sm tabular-nums">{result.ef_search}</td>
                  <td className="py-2 font-mono text-sm tabular-nums">
                    {result.min_similarity?.toFixed(2) ?? "—"}
                  </td>
                  <td className="py-2 font-mono text-sm">{result.index_build_mode ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-2 text-sm text-muted-foreground">
        <h2 className="text-lg font-semibold tracking-tight text-foreground">Methodology</h2>
        <pre className="overflow-x-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-xs">
          {JSON.stringify(run.methodology, null, 2)}
        </pre>
        {run.gate_summary ? (
          <pre className="overflow-x-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-xs">
            {JSON.stringify(run.gate_summary, null, 2)}
          </pre>
        ) : null}
      </section>
    </div>
  );
}
