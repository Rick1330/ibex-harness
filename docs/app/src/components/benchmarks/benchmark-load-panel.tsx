"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

export function BenchmarkLoadPanel() {
  const { latest, isLoading, isError, error } = useBenchmarkData();

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading load test data…</p>;
  }

  if (isError) {
    return (
      <p className="rounded-md border border-danger/30 bg-danger/5 p-4 text-sm text-danger">
        {error instanceof Error ? error.message : "Failed to load benchmark data"}
      </p>
    );
  }

  if (!latest) {
    return <BenchmarkEmptyState />;
  }

  const { k6 } = latest;

  return (
    <div className="space-y-8">
      <p className="text-sm text-muted-foreground">
        k6 load profile: {k6.vus} VUs · {Math.round(k6.duration_s)}s duration
      </p>
      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <KpiCard label="p50" value={formatMs(k6.p50_ms)} />
        <KpiCard label="p95" value={formatMs(k6.p95_ms)} />
        <KpiCard label="p99" value={formatMs(k6.p99_ms)} />
        <KpiCard label="p99.9" value={formatMs(k6.p999_ms)} />
        <KpiCard label="Throughput" value={formatReqPerSec(k6.req_per_s)} higherIsBetter />
        <KpiCard label="Checks" value={formatPercent(k6.check_rate)} higherIsBetter />
        <KpiCard label="Errors" value={formatPercent(k6.error_rate)} />
      </section>
    </div>
  );
}
