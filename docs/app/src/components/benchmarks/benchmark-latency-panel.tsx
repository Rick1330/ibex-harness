"use client";

import { RegressionAlert } from "@/components/benchmarks/regression-alert";
import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { AllocTrendChart } from "@/components/benchmarks/alloc-trend-chart";
import { ExportCsvButton } from "@/components/benchmarks/export-csv-button";
import { PercentileTrendChart } from "@/components/benchmarks/percentile-trend-chart";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { TimeRangePicker } from "@/components/benchmarks/time-range-picker";
import { TrendChart } from "@/components/benchmarks/trend-chart";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";
import { filterRunsByRange, parseTimeRange } from "@/lib/benchmarks/plot";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

function LatencyContent() {
  const { runs, latest, isLoading, isError, errorMessage } = useBenchmarkData();
  const searchParams = useSearchParams();
  const range = parseTimeRange(searchParams.get("range"));
  const filtered = filterRunsByRange(runs, range);
  const regressionRun = filtered.find((run) => run.status === "regression");

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

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <TimeRangePicker />
        <ExportCsvButton runs={runs} range={range} />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Proxy overhead percentiles
        </h2>
        <PercentileTrendChart runs={filtered} />
        <p className="mt-2 text-xs text-muted-foreground">
          p50 · p95 · p99 · p99.9 — dashed line is SLA target (20ms)
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Memory allocations
        </h2>
        <AllocTrendChart runs={filtered} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Throughput (req/s)
        </h2>
        <TrendChart
          runs={filtered}
          metric={(run) => run.k6.req_per_s}
          targetMs={undefined}
          showCiBand={false}
          yTickFormat={(value) => `${Math.round(value).toLocaleString("en-US")} req/s`}
        />
      </section>

      {regressionRun ? <RegressionAlert run={regressionRun} runs={runs} /> : null}
    </div>
  );
}

export function BenchmarkLatencyPanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[200px]" />}>
      <LatencyContent />
    </Suspense>
  );
}
