"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { CompareMetricsTable, type CompareMetricRow } from "@/components/benchmarks/compare-metrics-table";
import { CompareRunSelectors } from "@/components/benchmarks/compare-run-selectors";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { formatDeltaPct, formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { pctChange } from "@/lib/benchmarks/regression";
import { findRunBySha } from "@/lib/benchmarks/runs";
import type { BenchmarkRun } from "@/lib/benchmarks/types";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

function buildCompareMetricRows(baseRun: BenchmarkRun, headRun: BenchmarkRun): CompareMetricRow[] {
  return [
    {
      label: "Proxy p99",
      base: formatMs(baseRun.k6.p99_ms),
      head: formatMs(headRun.k6.p99_ms),
      delta: formatDeltaPct(pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms)),
      deltaValue: pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms),
    },
    {
      label: "Throughput",
      base: formatReqPerSec(baseRun.k6.req_per_s),
      head: formatReqPerSec(headRun.k6.req_per_s),
      delta: formatDeltaPct(pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true)),
      deltaValue: pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true),
      higherIsBetter: true,
    },
    {
      label: "Error rate",
      base: formatPercent(baseRun.k6.error_rate),
      head: formatPercent(headRun.k6.error_rate),
      delta: formatDeltaPct(pctChange(baseRun.k6.error_rate, headRun.k6.error_rate)),
      deltaValue: pctChange(baseRun.k6.error_rate, headRun.k6.error_rate),
    },
    {
      label: "Total overhead p99",
      base: formatMs(baseRun.stages.total_overhead_p99_ms),
      head: formatMs(headRun.stages.total_overhead_p99_ms),
      delta: formatDeltaPct(
        pctChange(baseRun.stages.total_overhead_p99_ms, headRun.stages.total_overhead_p99_ms),
      ),
      deltaValue: pctChange(baseRun.stages.total_overhead_p99_ms, headRun.stages.total_overhead_p99_ms),
    },
  ];
}

function CompareContent() {
  const { runs, isLoading, isError, error } = useBenchmarkData();
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
        message={error instanceof Error ? error.message : "Failed to load benchmark data"}
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
        onBaseChange={(value) => updateParam("base", value)}
        onHeadChange={(value) => updateParam("head", value)}
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
