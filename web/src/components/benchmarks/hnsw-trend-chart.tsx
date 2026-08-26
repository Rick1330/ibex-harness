"use client";

import { useRef } from "react";

import { ChartContainer } from "@/components/benchmarks/chart-container";
import { useChartTheme } from "@/hooks/use-chart-theme";
import { useRenderPlot } from "@/hooks/use-render-plot";
import type { HnswBenchmarkRun } from "@/lib/benchmarks/hnsw-schema";
import { buildTrendPlot } from "@/lib/benchmarks/plot-marks";
import type { TrendDatum } from "@/lib/benchmarks/plot";
import type { RunStatus } from "@/lib/benchmarks/types";

type HnswTrendChartProps = Readonly<{
  runs: readonly HnswBenchmarkRun[];
  metric: (run: HnswBenchmarkRun) => number | null;
  targetMs?: number;
  height?: number;
  yTickFormat?: (value: number) => string;
}>;

function toPlotStatus(status: HnswBenchmarkRun["status"]): RunStatus {
  if (status === "fail") return "fail";
  if (status === "warn") return "unknown";
  return "pass";
}

export function HnswTrendChart({
  runs,
  metric,
  targetMs,
  height = 200,
  yTickFormat,
}: HnswTrendChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const theme = useChartTheme();

  useRenderPlot(
    containerRef,
    (width) => {
      const data: TrendDatum[] = [...runs]
        .flatMap((run) => {
          const value = metric(run);
          if (value == null) return [];
          const row: TrendDatum = {
            date: new Date(run.timestamp),
            value,
            status: toPlotStatus(run.status),
            shortSha: run.short_sha,
            timestamp: run.timestamp,
            prLabel: run.branch,
            budgetPct: targetMs && targetMs > 0 ? (value / targetMs) * 100 : undefined,
          };
          return [row];
        })
        .sort((a, b) => a.date.getTime() - b.date.getTime());
      return buildTrendPlot(data, theme, {
        width,
        height,
        targetMs,
        yTickFormat,
        showCiBand: false,
      });
    },
    [runs, metric, targetMs, height, theme, yTickFormat],
  );

  if (runs.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No runs in the selected time range.</p>
    );
  }

  return <ChartContainer ref={containerRef} label="HNSW trend chart" />;
}
