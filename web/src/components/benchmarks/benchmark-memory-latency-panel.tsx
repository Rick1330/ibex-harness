"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { HnswTrendChart } from "@/components/benchmarks/hnsw-trend-chart";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { TimeRangePicker } from "@/components/benchmarks/time-range-picker";
import { HNSW_SLA_TARGETS } from "@/lib/benchmarks/constants";
import {
  corpusSizeLabel,
  filterHnswRunsByRange,
  resultAtCorpusSize,
  uniqueCorpusSizes,
} from "@/lib/benchmarks/hnsw-runs";
import { parseTimeRange } from "@/lib/benchmarks/plot";
import { useHnswBenchmarkData } from "@/hooks/use-hnsw-benchmark-data";

function MemoryLatencyContent() {
  const { runs, latest, isLoading, isError, errorMessage, refresh } = useHnswBenchmarkData();
  const searchParams = useSearchParams();
  const range = parseTimeRange(searchParams.get("range"));
  const filtered = filterHnswRunsByRange(runs, range);
  const sizes = uniqueCorpusSizes(filtered);

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

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="min-h-[320px] space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <TimeRangePicker />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Mean recall@10
        </h2>
        <HnswTrendChart
          runs={filtered}
          metric={(run) => run.mean_recall_at_10}
          targetMs={undefined}
          yTickFormat={(value) => `${(value * 100).toFixed(0)}%`}
        />
        <p className="mt-2 text-xs text-muted-foreground">
          Target ≥ {(HNSW_SLA_TARGETS.recall_at_10 * 100).toFixed(0)}%
        </p>
      </section>

      {sizes.map((size) => (
        <section key={size}>
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
            {corpusSizeLabel(size)} search latency (p95 / p99)
          </h2>
          <div className="space-y-4">
            <HnswTrendChart
              runs={filtered}
              metric={(run) => resultAtCorpusSize(run, size)?.latency_ms_p95 ?? null}
              targetMs={size >= 1_000_000 ? HNSW_SLA_TARGETS.p95_ms_1m : undefined}
              yTickFormat={(value) => `${value.toFixed(1)} ms`}
            />
            <HnswTrendChart
              runs={filtered}
              metric={(run) => resultAtCorpusSize(run, size)?.latency_ms_p99 ?? null}
              targetMs={size >= 1_000_000 ? HNSW_SLA_TARGETS.p99_ms_1m : undefined}
              yTickFormat={(value) => `${value.toFixed(1)} ms`}
            />
          </div>
        </section>
      ))}

      {filtered.length < 2 ? (
        <p className="text-sm text-muted-foreground">
          Trend charts fill in as more Memory Benchmarks runs publish to history.
        </p>
      ) : null}
    </div>
  );
}

export function BenchmarkMemoryLatencyPanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[200px]" />}>
      <MemoryLatencyContent />
    </Suspense>
  );
}
