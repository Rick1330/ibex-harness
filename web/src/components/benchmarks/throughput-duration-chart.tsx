"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { buildThroughputDurationPlot } from "@/lib/benchmarks/plot-marks";
import type { ThroughputPoint } from "@/lib/benchmarks/types";

type ThroughputDurationChartProps = Readonly<{
  series: ThroughputPoint[];
}>;

export function ThroughputDurationChart({ series }: ThroughputDurationChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => {
      if (series.length === 0) {
        return null;
      }
      return buildThroughputDurationPlot(series, theme, width);
    },
    [series, theme],
  );

  if (series.length === 0) {
    return <p className="text-sm text-muted-foreground">No throughput time-series for this run.</p>;
  }

  return <ChartContainer ref={containerRef} label="Throughput over test duration chart" />;
}
