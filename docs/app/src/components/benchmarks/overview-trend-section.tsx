import { TrendChart } from "@/components/benchmarks/trend-chart";
import { CHART_OVERVIEW_DAYS } from "@/lib/benchmarks/constants";
import { filterRunsByDays } from "@/lib/benchmarks/plot";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type OverviewTrendSectionProps = Readonly<{
  runs: BenchmarkRun[];
}>;

export function OverviewTrendSection({ runs }: OverviewTrendSectionProps) {
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
