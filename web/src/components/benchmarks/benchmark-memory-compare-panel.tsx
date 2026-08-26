"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { CompareMetricsTable } from "@/components/benchmarks/compare-metrics-table";
import { CompareRunSelectors } from "@/components/benchmarks/compare-run-selectors";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { buildHnswCompareMetricRows } from "@/lib/benchmarks/hnsw-compare-metrics";
import { findHnswRunBySha } from "@/lib/benchmarks/hnsw-runs";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

function MemoryCompareContent() {
  const { runs, isLoading, isError, errorMessage } = useHnswBenchmarkData();
  const router = useRouter();
  const searchParams = useSearchParams();
  const baseSha = searchParams.get("base") ?? "";
  const headSha = searchParams.get("head") ?? "";

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState message={errorMessage ?? "Failed to load HNSW benchmark data"} />
    );
  }

  if (runs.length === 0) {
    return <BenchmarkEmptyState />;
  }

  const baseRun = baseSha ? findHnswRunBySha(runs, baseSha) : (runs[1] ?? runs[0]);
  const headRun = headSha ? findHnswRunBySha(runs, headSha) : runs[0];

  if (!baseRun || !headRun) {
    return <BenchmarkEmptyState />;
  }

  function updateParam(key: "base" | "head", value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set(key, value);
    router.replace(`/benchmarks/memory/compare?${params.toString()}`);
  }

  return (
    <div className="space-y-6">
      <CompareRunSelectors
        runs={runs}
        baseSha={baseRun.short_sha}
        headSha={headRun.short_sha}
        onBaseChange={(value) => {
          updateParam("base", value);
        }}
        onHeadChange={(value) => {
          updateParam("head", value);
        }}
      />
      {runs.length < 2 ? (
        <p className="text-sm text-muted-foreground">
          Only one published run — deltas will appear once history accumulates.
        </p>
      ) : null}
      <CompareMetricsTable
        baseSha={baseRun.short_sha}
        headSha={headRun.short_sha}
        rows={buildHnswCompareMetricRows(baseRun, headRun)}
      />
    </div>
  );
}

export function BenchmarkMemoryComparePanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[200px]" />}>
      <MemoryCompareContent />
    </Suspense>
  );
}
