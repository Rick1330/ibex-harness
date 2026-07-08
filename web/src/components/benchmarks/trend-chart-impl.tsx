"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { K6_TARGETS } from "@/lib/benchmarks/constants";
import { buildTrendPlot } from "@/lib/benchmarks/plot-marks";
import { toTrendData, type TrendDatum } from "@/lib/benchmarks/plot";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type TrendChartImplProps = Readonly<{
  runs: BenchmarkRun[];
  metric?: (run: BenchmarkRun) => number;
  targetMs?: number;
  height?: number;
  yTickFormat?: (value: number) => string;
  showCiBand?: boolean;
}>;

function proxyP99(run: BenchmarkRun): number {
  return run.k6.p99_ms;
}

function proxyCi(run: BenchmarkRun): { low: number; high: number } | null {
  const bench = run.go_benchmarks.BenchmarkProxyOverhead;
  if (!bench) {
    return null;
  }
  return {
    low: bench.ci_95_low / 1e6,
    high: bench.ci_95_high / 1e6,
  };
}

export function TrendChartImpl({
  runs,
  metric = proxyP99,
  targetMs = K6_TARGETS.p99_ms,
  height = 200,
  yTickFormat,
  showCiBand = true,
}: TrendChartImplProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => {
      const data: TrendDatum[] = toTrendData(
        runs,
        metric,
        showCiBand ? proxyCi : undefined,
        targetMs,
      );
      return buildTrendPlot(data, theme, {
        width,
        height,
        targetMs,
        yTickFormat,
        showCiBand,
      });
    },
    [runs, metric, targetMs, height, theme, yTickFormat, showCiBand],
  );

  if (runs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No runs in the selected time range.</p>
    );
  }

  return <ChartContainer ref={containerRef} label="Trend chart" />;
}
