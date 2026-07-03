"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { buildWaterfallPlot } from "@/lib/benchmarks/plot-marks";
import type { StageLatency } from "@/lib/benchmarks/types";

type WaterfallChartProps = Readonly<{
  stages: StageLatency;
}>;

export function WaterfallChart({ stages }: WaterfallChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => buildWaterfallPlot(stages, theme, theme.isDark, width),
    [stages, theme],
  );

  return <ChartContainer ref={containerRef} label="Stage waterfall chart" />;
}
