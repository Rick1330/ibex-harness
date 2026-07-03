"use client";

import Link from "next/link";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { KpiCard } from "@/components/benchmarks/kpi-card";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { PercentileChart } from "@/components/benchmarks/percentile-chart";
import { RunMeta } from "@/components/benchmarks/run-meta";
import { BenchmarkStatusBadge } from "@/components/benchmarks/status-badge";
import { WaterfallChart } from "@/components/benchmarks/waterfall-chart";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";
import {
  formatBytes,
  formatMs,
  formatPercent,
  formatReqPerSec,
} from "@/lib/benchmarks/format";
import { findRunBySha } from "@/lib/benchmarks/runs";

type BenchmarkRunDetailPanelProps = Readonly<{
  sha: string;
}>;

export function BenchmarkRunDetailPanel({ sha }: BenchmarkRunDetailPanelProps) {
  const { runs, data, isLoading, isError, error } = useBenchmarkData();

  if (isLoading) {
    return <ChartSkeleton className="h-[220px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={error instanceof Error ? error.message : "Failed to load benchmark data"}
      />
    );
  }

  const run = findRunBySha(runs, sha);
  if (!run) {
    return <BenchmarkEmptyState />;
  }

  const baseline = data?.baseline_sha ? findRunBySha(runs, data.baseline_sha) : null;
  const overhead = run.go_benchmarks.BenchmarkProxyOverhead;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Link
          href="/benchmarks/history"
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          ← Back to history
        </Link>
        <Link
          href={`/benchmarks/compare?base=${baseline?.short_sha ?? run.short_sha}&head=${run.short_sha}`}
          className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          Compare to baseline
        </Link>
      </div>

      <div className="space-y-2">
        <BenchmarkStatusBadge run={run} />
        <RunMeta run={run} />
      </div>

      <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Proxy p99"
          value={formatMs(run.k6.p99_ms)}
          deltaPct={run.metric_deltas?.["k6.p99_ms"] ?? run.regression_vs_baseline_pct}
        />
        <KpiCard
          label="Throughput"
          value={formatReqPerSec(run.k6.req_per_s)}
          deltaPct={run.metric_deltas?.["k6.req_per_s"] ?? null}
          higherIsBetter
        />
        <KpiCard
          label="Allocs/op"
          value={overhead ? formatBytes(overhead.bytes_per_op) : "—"}
        />
        <KpiCard label="Error rate" value={formatPercent(run.k6.error_rate)} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Stage breakdown
        </h2>
        <WaterfallChart stages={run.stages} />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold uppercase tracking-widest text-muted-foreground">
          Latency percentiles
        </h2>
        <PercentileChart run={run} />
      </section>
    </div>
  );
}
