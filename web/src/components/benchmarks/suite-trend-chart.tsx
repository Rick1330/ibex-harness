"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { buildTrendPlot } from "@/lib/benchmarks/plot-marks";
import type { TrendDatum } from "@/lib/benchmarks/plot";

type SuiteTrendChartProps = Readonly<{
  data: readonly TrendDatum[];
  targetMs?: number;
  height?: number;
  yTickFormat?: (value: number) => string;
  showCiBand?: boolean;
}>;

export function SuiteTrendChart({
  data,
  targetMs,
  height = 200,
  yTickFormat,
  showCiBand = false,
}: SuiteTrendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => {
      if (data.length === 0) {
        return null;
      }
      return buildTrendPlot([...data], theme, {
        width,
        height,
        targetMs,
        yTickFormat,
        showCiBand,
      });
    },
    [data, targetMs, height, theme, yTickFormat, showCiBand],
  );

  if (data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No runs in the selected time range.</p>
    );
  }

  return <ChartContainer ref={containerRef} label="Suite trend chart" />;
}
