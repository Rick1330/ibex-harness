"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { HistoryTable } from "@/components/benchmarks/history-table";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

export function BenchmarkHistoryPanel() {
  const { runs, isLoading, isError, error } = useBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={error instanceof Error ? error.message : "Failed to load benchmark data"}
      />
    );
  }

  if (runs.length === 0) {
    return <BenchmarkEmptyState />;
  }

  return <HistoryTable runs={runs} />;
}
