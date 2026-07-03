import { KpiCard } from "@/components/benchmarks/kpi-card";
import { formatBytes, formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type RunDetailKpiGridProps = Readonly<{
  run: BenchmarkRun;
}>;

export function RunDetailKpiGrid({ run }: RunDetailKpiGridProps) {
  const overhead = run.go_benchmarks.BenchmarkProxyOverhead;

  return (
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
        label="Bytes/op"
        value={overhead ? formatBytes(overhead.bytes_per_op) : "—"}
      />
      <KpiCard label="Error rate" value={formatPercent(run.k6.error_rate)} />
    </section>
  );
}
