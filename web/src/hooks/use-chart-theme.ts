import { useTheme } from "next-themes";
import { useMemo } from "react";

import {
  CHART_PRIMARY_LINE_DARK,
  CHART_PRIMARY_LINE_LIGHT,
  CHART_SERIES_DARK,
  CHART_SERIES_DUAL_DARK,
  CHART_SERIES_DUAL_LIGHT,
  CHART_SERIES_LIGHT,
} from "@/lib/benchmarks/chart-colors";

export interface ChartTheme {
  isDark: boolean;
  line: string;
  primaryLine: string;
  lineMuted: string;
  area: string;
  grid: string;
  axis: string;
  tip: string;
  tipBorder: string;
  tipText: string;
  danger: string;
  warning: string;
  target: string;
  success: string;
  series: readonly [string, string, string, string];
  seriesDual: readonly [string, string];
}

const LIGHT: ChartTheme = {
  isDark: false,
  line: "hsl(240 10% 4%)",
  primaryLine: CHART_PRIMARY_LINE_LIGHT,
  lineMuted: "hsl(240 5% 65%)",
  area: "hsl(213 94% 68% / 0.14)",
  grid: "hsl(240 5% 90%)",
  axis: "hsl(240 5% 65%)",
  tip: "hsl(240 5% 96%)",
  tipBorder: "hsl(240 5% 84%)",
  tipText: "hsl(240 10% 4%)",
  danger: "hsl(0 72% 51%)",
  warning: "hsl(32 95% 44%)",
  target: "hsl(240 5% 84%)",
  success: "hsl(142 71% 35%)",
  series: CHART_SERIES_LIGHT,
  seriesDual: CHART_SERIES_DUAL_LIGHT,
};

const DARK: ChartTheme = {
  isDark: true,
  line: "hsl(0 0% 98%)",
  primaryLine: CHART_PRIMARY_LINE_DARK,
  lineMuted: "hsl(240 4% 46%)",
  area: "hsl(213 94% 68% / 0.18)",
  grid: "hsl(240 5% 14%)",
  axis: "hsl(240 4% 46%)",
  tip: "hsl(240 6% 7%)",
  tipBorder: "hsl(240 4% 21%)",
  tipText: "hsl(0 0% 98%)",
  danger: "hsl(0 91% 71%)",
  warning: "hsl(38 92% 50%)",
  target: "hsl(240 4% 21%)",
  success: "hsl(142 69% 58%)",
  series: CHART_SERIES_DARK,
  seriesDual: CHART_SERIES_DUAL_DARK,
};

export function useChartTheme(): ChartTheme {
  const { resolvedTheme } = useTheme();
  return useMemo(() => (resolvedTheme === "dark" ? DARK : LIGHT), [resolvedTheme]);
}
