import type { ChartTheme } from "@/hooks/use-chart-theme";

export type SeriesTrendPreset = Readonly<{
  height?: number;
  targetMs?: number;
  yLabel?: string;
  legendDomain: string[];
  legendRange: readonly string[];
}>;

export function percentileSeriesPreset(theme: ChartTheme, targetMs: number): SeriesTrendPreset {
  return {
    height: 220,
    targetMs,
    legendDomain: ["p50", "p95", "p99", "p99.9"],
    legendRange: theme.series,
  };
}

export function allocSeriesPreset(theme: ChartTheme): SeriesTrendPreset {
  return {
    yLabel: "KB / allocs",
    legendDomain: ["bytes/op", "allocs/op"],
    legendRange: theme.seriesDual,
  };
}
