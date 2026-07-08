"use client";

import { useMemo, useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import { K6_TARGETS } from "@/lib/benchmarks/constants";
import { buildStageStackPlot } from "@/lib/benchmarks/plot-marks";
import { filterRunsByDays, toStageStackData } from "@/lib/benchmarks/plot";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

type StageStackChartProps = Readonly<{
  runs: BenchmarkRun[];
  days?: number;
}>;

export function StageStackChart({ runs, days = 30 }: StageStackChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();
  const filtered = useMemo(() => filterRunsByDays(runs, days), [runs, days]);

  useRenderPlot(
    containerRef,
    (width) => {
      const data = toStageStackData(filtered);
      if (data.length === 0) {
        return null;
      }
      return buildStageStackPlot(data, theme, width, K6_TARGETS.p99_ms);
    },
    [filtered, theme],
  );

  if (filtered.length === 0) {
    return <p className="text-sm text-muted-foreground">No stage history in range.</p>;
  }

  return <ChartContainer ref={containerRef} label="Stage trend stacked area chart" />;
}
