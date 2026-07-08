import { KpiCard } from "@/components/benchmarks/kpi-card";
import { K6_TARGETS } from "@/lib/benchmarks/constants";
import { formatBytes, formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { proxyOverheadBenchmark } from "@/lib/benchmarks/run-benchmarks";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type OverviewKpiGridProps = Readonly<{
  latest: BenchmarkRun;
}>;

export function OverviewKpiGrid({ latest }: OverviewKpiGridProps) {
  const overhead = proxyOverheadBenchmark(latest);
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
