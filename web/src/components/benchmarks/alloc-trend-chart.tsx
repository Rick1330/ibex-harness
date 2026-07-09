"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { allocSeriesPreset } from "@/lib/benchmarks/plot-series-presets";
import { buildSeriesTrendPlot } from "@/lib/benchmarks/plot-marks";
import { toAllocTrendData } from "@/lib/benchmarks/plot";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type AllocTrendChartProps = Readonly<{
  runs: BenchmarkRun[];
}>;

export function AllocTrendChart({ runs }: AllocTrendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => {
      const data = toAllocTrendData(runs);
      if (data.length === 0) {
        return null;
      }
      return buildSeriesTrendPlot(data, theme, allocSeriesPreset(theme), width);
    },
    [runs, theme],
  );

  if (runs.length === 0) {
    return <p className="text-sm text-muted-foreground">No allocation history in range.</p>;
  }

  return <ChartContainer ref={containerRef} label="Allocation trend chart" />;
}
