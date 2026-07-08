"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { OverviewKpiGrid } from "@/components/benchmarks/overview-kpi-grid";
import { OverviewSlaSection } from "@/components/benchmarks/overview-sla-section";
import { OverviewTrendSection } from "@/components/benchmarks/overview-trend-section";
import {
  KpiCardSkeleton,
  StatusBadgeSkeleton,
} from "@/components/benchmarks/kpi-card-skeleton";
import { RegressionAlert } from "@/components/benchmarks/regression-alert";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { BenchmarkStatusBadge } from "@/components/benchmarks/status-badge";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

const OVERVIEW_KPI_SKELETONS = ["proxy-p99", "throughput", "allocs", "error-rate"] as const;

export function BenchmarkOverviewPanel() {
  const { latest, runs, isLoading, isError, errorMessage } = useBenchmarkData();

  if (isLoading) {
    return (
      <div className="space-y-8">
        <StatusBadgeSkeleton />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {OVERVIEW_KPI_SKELETONS.map((key) => (
            <KpiCardSkeleton key={key} />
          ))}
        </div>
        <ChartSkeleton />
      </div>
    );
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load benchmark data"}
      />
    );
  }

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="space-y-8">
      <RegressionAlert run={latest} />
      <BenchmarkStatusBadge run={latest} />
      <OverviewKpiGrid latest={latest} />
      <section className="grid gap-4 lg:grid-cols-3">
        <OverviewTrendSection runs={runs} />
        <OverviewSlaSection latest={latest} />
      </section>
    </div>
  );
}
