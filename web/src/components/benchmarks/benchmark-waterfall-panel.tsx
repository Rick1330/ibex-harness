"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { StageDetailsTable } from "@/components/benchmarks/stage-details-table";
import { StageStackChart } from "@/components/benchmarks/stage-stack-chart";
import { WaterfallChart } from "@/components/benchmarks/waterfall-chart";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

export function BenchmarkWaterfallPanel() {
  const { latest, runs, isLoading, isError, errorMessage } = useBenchmarkData();

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

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  return (
    <div className="space-y-8">
      <p className="font-mono text-sm text-muted-foreground">
        Current run: {latest.short_sha} · {new Date(latest.timestamp).toLocaleDateString()}
      </p>

      <section>
        <h2 className="mb-1 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Stage waterfall (p99)
        </h2>
        <p className="mb-3 text-sm text-muted-foreground">
          Synthetic Go microbench decomposition. Authoritative end-to-end latency is k6 p99.
        </p>
        <WaterfallChart stages={latest.stages} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Stage trend (last 30 days)
        </h2>
        <StageStackChart runs={runs} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Stage details
        </h2>
        <StageDetailsTable stages={latest.stages} stageModel={latest.stage_model} />
      </section>
    </div>
  );
}
