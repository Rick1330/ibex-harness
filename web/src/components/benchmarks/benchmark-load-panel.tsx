"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { PercentileChart } from "@/components/benchmarks/percentile-chart";
import { ThroughputDurationChart } from "@/components/benchmarks/throughput-duration-chart";
import { K6_TARGETS } from "@/lib/benchmarks/constants";
import { formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

export function BenchmarkLoadPanel() {
  const { latest, isLoading, isError, errorMessage } = useBenchmarkData();

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

  const { k6 } = latest;
  const errorOk = k6.error_rate <= K6_TARGETS.error_rate;
  const p99Ok = k6.p99_ms <= K6_TARGETS.p99_ms;

  return (
    <div className="space-y-8">
      <p className="text-sm text-muted-foreground">
        k6 · {k6.vus} VUs · {Math.round(k6.duration_s)}s · mock provider (no real OpenAI calls)
      </p>

      <section className="grid min-h-[88px] gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="p99 latency"
          value={formatMs(k6.p99_ms)}
          hint={p99Ok ? "✓ < 20ms" : "✗ above target"}
        />
        <KpiCard label="Throughput" value={formatReqPerSec(k6.req_per_s)} higherIsBetter />
        <KpiCard
          label="Error rate"
          value={formatPercent(k6.error_rate)}
          hint={errorOk ? "✓ < 0.1%" : "✗ above target"}
        />
        <KpiCard
          label="Duration"
          value={`${Math.round(k6.duration_s)}s`}
          hint={`${k6.vus} VUs`}
        />
      </section>

      <section className="rounded-md border border-border bg-card p-5">
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          k6 script
        </h2>
        <p className="font-mono text-xs text-muted-foreground">
          benchmarks/k6/proxy_load.js
        </p>
        <p className="mt-2 font-mono text-xs text-muted-foreground">
          vus: {k6.vus} · duration: {Math.round(k6.duration_s)}s · thresholds: p(99)&lt;
          {K6_TARGETS.p99_ms}ms · error_rate&lt;{K6_TARGETS.error_rate}
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Latency distribution
        </h2>
        <PercentileChart run={latest} />
        <p className="mt-2 text-xs text-muted-foreground">
          Dashed line marks SLA target ({K6_TARGETS.p99_ms}ms)
        </p>
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Throughput over test duration
        </h2>
        <ThroughputDurationChart series={k6.throughput_series ?? []} />
      </section>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="p50" value={formatMs(k6.p50_ms)} />
        <KpiCard label="p95" value={formatMs(k6.p95_ms)} />
        <KpiCard label="p99.9" value={formatMs(k6.p999_ms)} />
        <KpiCard label="Checks" value={formatPercent(k6.check_rate)} higherIsBetter />
      </section>
    </div>
  );
}
