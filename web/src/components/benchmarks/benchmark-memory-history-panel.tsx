"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { SuiteHistoryTable } from "@/components/benchmarks/suite-history-table";
import {
  corpusSizeLabel,
  formatRecallPct,
  largestCorpusResult,
} from "@/lib/benchmarks/hnsw-runs";
import type { HnswBenchmarkRun } from "@/lib/benchmarks/hnsw-schema";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

function HnswHistoryRunLink({ run }: Readonly<{ run: HnswBenchmarkRun }>) {
  return (
    <Link
      href={`/benchmarks/memory/history/${run.run_number}`}
      className="underline-offset-2 hover:underline"
    >
      {run.run_number}
    </Link>
  );
}

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
    <SuiteHistoryTable
      rows={runs}
      rowKey={(run) => run.run_number}
      getStatus={(run) => run.status ?? "unknown"}
      getBranch={(run) => run.branch}
      csvFilename="hnsw-history.csv"
      columns={[
        {
          header: "Run #",
          cell: (run) => <HnswHistoryRunLink run={run} />,
          csv: (run) => run.run_number,
        },
        { header: "SHA", cell: (run) => run.short_sha, csv: (run) => run.short_sha },
        { header: "Branch", cell: (run) => run.branch, csv: (run) => run.branch },
        {
          header: "Status",
          cell: (run) => (run.status ?? "unknown").toUpperCase(),
          csv: (run) => run.status ?? "unknown",
        },
        {
          header: "Mean recall",
          cell: (run) => formatRecallPct(run.mean_recall_at_10),
          csv: (run) => run.mean_recall_at_10,
        },
        {
          header: "Largest p95",
          cell: (run) => {
            const largest = largestCorpusResult(run);
            return largest ? `${largest.latency_ms_p95.toFixed(2)} ms` : "—";
          },
          csv: (run) => largestCorpusResult(run)?.latency_ms_p95 ?? "",
        },
        {
          header: "Sizes",
          cell: (run) => run.results.map((r) => corpusSizeLabel(r.corpus_size)).join(" · "),
          csv: (run) => run.results.map((r) => r.corpus_size).join("|"),
        },
        {
          header: "When",
          cell: (run) => run.timestamp,
          csv: (run) => run.timestamp,
          className: "px-4 py-3 font-mono text-xs text-muted-foreground",
        },
      ]}
    />
  );
}
