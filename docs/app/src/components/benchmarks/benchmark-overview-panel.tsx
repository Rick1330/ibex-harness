"use client";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import {
  KpiCardSkeleton,
  StatusBadgeSkeleton,
} from "@/components/benchmarks/kpi-card-skeleton";
import { RegressionAlert } from "@/components/benchmarks/regression-alert";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { TrendChart } from "@/components/benchmarks/trend-chart";
import { SlaGauge } from "@/components/benchmarks/sla-gauge";
import { BenchmarkStatusBadge } from "@/components/benchmarks/status-badge";
import { K6_TARGETS, SLA_TARGETS, CHART_OVERVIEW_DAYS } from "@/lib/benchmarks/constants";
import {
  formatBytes,
  formatMs,
  formatPercent,
  formatReqPerSec,
} from "@/lib/benchmarks/format";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";
import { filterRunsByDays } from "@/lib/benchmarks/plot";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

const OVERVIEW_KPI_SKELETONS = ["proxy-p99", "throughput", "allocs", "error-rate"] as const;

function proxyOverhead(run: BenchmarkRun) {
  return run.go_benchmarks.BenchmarkProxyOverhead;
}

function OverviewKpiGrid({ latest }: Readonly<{ latest: BenchmarkRun }>) {
  const overhead = proxyOverhead(latest);
  const errorOk = latest.k6.error_rate <= K6_TARGETS.error_rate;
  const allocsDelta = latest.metric_deltas?.["go_benchmarks.BenchmarkProxyOverhead.bytes_per_op"];

  return (
    <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="Proxy p99"
        value={formatMs(latest.k6.p99_ms)}
        deltaPct={latest.metric_deltas?.["k6.p99_ms"] ?? latest.regression_vs_baseline_pct}
      />
      <KpiCard
        label="Throughput"
        value={formatReqPerSec(latest.k6.req_per_s)}
        deltaPct={latest.metric_deltas?.["k6.req_per_s"] ?? null}
        higherIsBetter
      />
      <KpiCard
        label="Allocs/op"
        value={overhead ? formatBytes(overhead.bytes_per_op) : "—"}
        deltaPct={allocsDelta ?? null}
      />
      <KpiCard
        label="Error rate"
        value={formatPercent(latest.k6.error_rate)}
        hint={errorOk ? "✓ target < 0.1%" : "✗ above target"}
      />
    </section>
  );
}

function OverviewSlaSection({ latest }: Readonly<{ latest: BenchmarkRun }>) {
  return (
    <div className="rounded-md border border-border bg-card p-5 lg:col-span-1">
      <h2 className="mb-4 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        SLA targets
      </h2>
      <div className="space-y-4">
        <SlaGauge label="Proxy overhead p99" valueMs={latest.k6.p99_ms} targetMs={K6_TARGETS.p99_ms} />
        <SlaGauge
          label="Auth LRU hit"
          valueMs={latest.stages.auth_lru_p99_ms}
          targetMs={SLA_TARGETS.auth_lru_hit_p99_ms}
        />
        <SlaGauge
          label="Auth gRPC fallback"
          valueMs={latest.stages.auth_grpc_p99_ms}
          targetMs={SLA_TARGETS.auth_grpc_fallback_p99_ms}
        />
        <SlaGauge
          label="Rate limit"
          valueMs={latest.stages.rate_limit_p99_ms}
          targetMs={SLA_TARGETS.rate_limit_p99_ms}
        />
        <SlaGauge
          label="Directive resolve"
          valueMs={latest.stages.directive_resolve_p99_ms}
          targetMs={SLA_TARGETS.directive_resolve_p99_ms}
        />
        <SlaGauge
          label="Error rate"
          valueMs={latest.k6.error_rate * 1000}
          targetMs={K6_TARGETS.error_rate * 1000}
        />
      </div>
    </div>
  );
}

function OverviewTrendSection({ runs }: Readonly<{ runs: BenchmarkRun[] }>) {
  const trendRuns = filterRunsByDays(runs, CHART_OVERVIEW_DAYS);

  return (
    <div className="lg:col-span-2">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
        Proxy p99 — last {CHART_OVERVIEW_DAYS} days
      </h2>
      <TrendChart runs={trendRuns} />
      <p className="mt-2 text-xs text-muted-foreground">
        Dashed line = SLA target (20ms) · dots = data points · red dots = regression runs
      </p>
    </div>
  );
}

export function BenchmarkOverviewPanel() {
  const { latest, runs, isLoading, isError, error } = useBenchmarkData();

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
        message={error instanceof Error ? error.message : "Failed to load benchmark data"}
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
