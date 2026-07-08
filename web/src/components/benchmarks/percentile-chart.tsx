"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { buildPercentilePlot } from "@/lib/benchmarks/plot-marks";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type PercentileChartProps = Readonly<{
  run: BenchmarkRun;
}>;

export function PercentileChart({ run }: PercentileChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => buildPercentilePlot(run, theme, width),
    [run, theme],
  );

  return <ChartContainer ref={containerRef} label="k6 percentile distribution chart" />;
}
