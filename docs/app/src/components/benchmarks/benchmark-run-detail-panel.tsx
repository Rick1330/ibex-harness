"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { RunDetailCharts } from "@/components/benchmarks/run-detail-charts";
import { RunDetailKpiGrid } from "@/components/benchmarks/run-detail-kpi-grid";
import { RunMeta } from "@/components/benchmarks/run-meta";
import { BenchmarkStatusBadge } from "@/components/benchmarks/status-badge";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";
import { findRunBySha } from "@/lib/benchmarks/runs";

type BenchmarkRunDetailPanelProps = Readonly<{
  sha: string;
}>;

export function BenchmarkRunDetailPanel({ sha }: BenchmarkRunDetailPanelProps) {
  const { runs, data, isLoading, isError, errorMessage } = useBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[220px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load benchmark data"}
      />
    );
  }

  const run = findRunBySha(runs, sha);
  if (!run) {
    return <BenchmarkEmptyState />;
  }

  const baseline = data?.baseline_sha ? findRunBySha(runs, data.baseline_sha) : null;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/benchmarks/history"
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          ← Back to history
        </Link>
        <Link
          href={`/benchmarks/compare?base=${baseline?.short_sha ?? run.short_sha}&head=${run.short_sha}`}
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Compare to baseline
        </Link>
      </div>

      <div className="space-y-2">
        <BenchmarkStatusBadge run={run} />
        <RunMeta run={run} />
      </div>

      <RunDetailKpiGrid run={run} />
      <RunDetailCharts run={run} />
    </div>
  );
}
