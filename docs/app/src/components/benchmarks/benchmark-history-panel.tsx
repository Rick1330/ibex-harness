"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { formatMs, formatReqPerSec } from "@/lib/benchmarks/format";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

export function BenchmarkHistoryPanel() {
  const { runs, isLoading, isError, error } = useBenchmarkData();

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading run history…</p>;
  }

  if (isError) {
    return (
      <p className="rounded-md border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
        {error instanceof Error ? error.message : "Failed to load benchmark data"}
      </p>
    );
  }

  if (runs.length === 0) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="min-w-full text-left text-sm">
        <thead className="border-b border-border bg-muted/40">
          <tr>
            <th className="px-4 py-3 font-medium text-muted-foreground">SHA</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">Branch</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">Status</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">p99</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">req/s</th>
            <th className="px-4 py-3 font-medium text-muted-foreground">When</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.sha} className="border-b border-border/70 last:border-0">
              <td className="px-4 py-3 font-mono text-xs">{run.short_sha}</td>
              <td className="px-4 py-3">{run.branch}</td>
              <td className="px-4 py-3 font-mono text-xs uppercase">{run.status}</td>
              <td className="px-4 py-3 font-mono tabular-nums">{formatMs(run.k6.p99_ms)}</td>
              <td className="px-4 py-3 font-mono tabular-nums">
                {formatReqPerSec(run.k6.req_per_s)}
              </td>
              <td className="px-4 py-3 text-muted-foreground">
                {run.run_url ? (
                  <a
                    href={run.run_url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline-offset-4 hover:underline"
                  >
                    {new Date(run.timestamp).toLocaleString()}
                  </a>
                ) : (
                  new Date(run.timestamp).toLocaleString()
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
