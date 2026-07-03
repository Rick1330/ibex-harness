import { PercentileChart } from "@/components/benchmarks/percentile-chart";
import { WaterfallChart } from "@/components/benchmarks/waterfall-chart";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type RunDetailChartsProps = Readonly<{
  run: BenchmarkRun;
}>;

export function RunDetailCharts({ run }: RunDetailChartsProps) {
  return (
    <>
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
    </>
  );
}
