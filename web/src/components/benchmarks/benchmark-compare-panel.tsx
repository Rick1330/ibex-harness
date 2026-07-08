"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { CompareMetricsTable } from "@/components/benchmarks/compare-metrics-table";
import { CompareRunSelectors } from "@/components/benchmarks/compare-run-selectors";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { buildCompareMetricRows } from "@/lib/benchmarks/compare-metrics";
import { findRunBySha } from "@/lib/benchmarks/runs";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

function CompareContent() {
  const { runs, isLoading, isError, errorMessage } = useBenchmarkData();
  const router = useRouter();
  const searchParams = useSearchParams();
  const baseSha = searchParams.get("base") ?? "";
  const headSha = searchParams.get("head") ?? "";

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={errorMessage ?? "Failed to load benchmark data"}
      />
    );
  }

  if (runs.length === 0) {
    return <BenchmarkEmptyState />;
  }

  const baseRun = baseSha ? findRunBySha(runs, baseSha) : runs[1] ?? runs[0];
  const headRun = headSha ? findRunBySha(runs, headSha) : runs[0];

  if (!baseRun || !headRun) {
    return <BenchmarkEmptyState />;
  }

  function updateParam(key: "base" | "head", value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set(key, value);
    router.replace(`/benchmarks/compare?${params.toString()}`);
  }

  return (
    <div className="space-y-6">
      <CompareRunSelectors
        runs={runs}
        baseSha={baseRun.short_sha}
        headSha={headRun.short_sha}
        onBaseChange={(value) => { updateParam("base", value); }}
        onHeadChange={(value) => { updateParam("head", value); }}
      />
      <CompareMetricsTable
        baseSha={baseRun.short_sha}
        headSha={headRun.short_sha}
        rows={buildCompareMetricRows(baseRun, headRun)}
      />
    </div>
  );
}

export function BenchmarkComparePanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[200px]" />}>
      <CompareContent />
    </Suspense>
  );
}
