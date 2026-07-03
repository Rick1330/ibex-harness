"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { K6_TARGETS } from "@/lib/benchmarks/constants";
import { buildSeriesTrendPlot } from "@/lib/benchmarks/plot-marks";
import { percentileSeriesPreset } from "@/lib/benchmarks/plot-series-presets";
import { toPercentileTrendData } from "@/lib/benchmarks/plot";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type PercentileTrendChartProps = Readonly<{
  runs: BenchmarkRun[];
}>;

export function PercentileTrendChart({ runs }: PercentileTrendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => {
      const data = toPercentileTrendData(runs);
      if (data.length === 0) {
        return null;
      }
      return buildSeriesTrendPlot(
        data,
        theme,
        percentileSeriesPreset(theme, K6_TARGETS.p99_ms),
        width,
      );
    },
    [runs, theme],
  );

  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">No percentile history in range.</p>;
  }

  return <ChartContainer ref={containerRef} label="Percentile trend chart" />;
}
