"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { BenchmarkStatusBadge } from "@/components/benchmarks/status-badge";
import { SLA_TARGETS, K6_TARGETS } from "@/lib/benchmarks/constants";
import { formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

export function BenchmarkOverviewPanel() {
  const { latest, isLoading, isError, error } = useBenchmarkData();

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading benchmark data…</p>;
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

  return (
    <div className="space-y-8">
      <BenchmarkStatusBadge run={latest} />

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Proxy p99"
          value={formatMs(latest.k6.p99_ms)}
          deltaPct={latest.regression_vs_baseline_pct}
        />
        <KpiCard
          label="Throughput"
          value={formatReqPerSec(latest.k6.req_per_s)}
          higherIsBetter
        />
        <KpiCard label="Error rate" value={formatPercent(latest.k6.error_rate)} />
        <KpiCard
          label="Stage total"
          value={formatMs(latest.stages.total_overhead_p99_ms)}
        />
      </section>

      <section className="rounded-md border border-border bg-card p-5">
        <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          SLA budget
        </h2>
        <div className="space-y-4">
          <SlaGauge
            label="k6 p99"
            valueMs={latest.k6.p99_ms}
            targetMs={K6_TARGETS.p99_ms}
          />
          <SlaGauge
            label="Total overhead"
            valueMs={latest.stages.total_overhead_p99_ms}
            targetMs={SLA_TARGETS.total_overhead_p99_ms}
          />
          <SlaGauge
            label="Rate limit"
            valueMs={latest.stages.rate_limit_p99_ms}
            targetMs={SLA_TARGETS.rate_limit_p99_ms}
          />
        </div>
      </section>
    </div>
  );
}
