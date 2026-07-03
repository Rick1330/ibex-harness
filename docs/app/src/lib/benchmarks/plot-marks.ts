import * as Plot from "@observablehq/plot";

import type { ChartTheme } from "@/hooks/use-chart-theme";
import { formatTrendTipTitle } from "@/lib/benchmarks/chart-tooltips";
import {
  otherOverheadColor,
  stageColor,
  STAGE_LABELS,
  type StageKey,
} from "@/lib/benchmarks/chart-colors";
import type { BenchmarkRun, StageLatency } from "@/lib/benchmarks/types";
import type { SeriesTrendPreset } from "@/lib/benchmarks/plot-series-presets";

import type {
  StageStackRow,
  ThroughputDurationDatum,
  TrendDatum,
} from "@/lib/benchmarks/plot";

const STACK_STAGE_KEYS: StageKey[] = [
  "auth_lru_p99_ms",
  "auth_grpc_p99_ms",
  "rate_limit_p99_ms",
  "directive_resolve_p99_ms",
  "prompt_inject_p99_ms",
];

function plotMonoStyle(theme: ChartTheme): NonNullable<Plot.PlotOptions["style"]> {
  return {
    color: theme.axis,
    fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
    fontSize: "11px",
  };
}

function lineDotMarks<T extends object>(
  data: T[],
  opts: Readonly<{
    x: string;
    y: string;
    stroke: string;
    fill?: string;
    strokeWidth?: number;
    dotRadius?: number;
    z?: string | null;
  }>,
): Plot.Markish[] {
  return [
    Plot.line(data, {
      x: opts.x,
      y: opts.y,
      stroke: opts.stroke,
      strokeWidth: opts.strokeWidth ?? 2,
      z: opts.z ?? null,
    }),
    Plot.dot(data, {
      x: opts.x,
      y: opts.y,
      fill: opts.fill ?? opts.stroke,
      r: opts.dotRadius ?? 2,
    }),
  ];
}

function trendAxisMarks(
  theme: ChartTheme,
  yTickFormat: (value: number) => string,
): Plot.Markish[] {
  return [
    Plot.gridY({ stroke: theme.grid, strokeOpacity: 1 }),
    Plot.axisX({
      tickSize: 0,
      stroke: theme.axis,
      tickFormat: "%b %d",
    }),
    Plot.axisY({
      tickSize: 0,
      stroke: theme.axis,
      tickFormat: yTickFormat,
      label: null,
    }),
  ];
}

function trendSeriesMarks(
  data: TrendDatum[],
  theme: ChartTheme,
  showCiBand: boolean,
): Plot.Markish[] {
  const regressionData = data.filter((point) => point.status === "regression");
  const bandData = data.filter(
    (point) => point.ciLow !== undefined && point.ciHigh !== undefined,
  );
  const marks: Plot.Markish[] = [];

  if (showCiBand && bandData.length > 0) {
    marks.push(
      Plot.areaY(bandData, {
        x: "date",
        y1: "ciLow",
        y2: "ciHigh",
        fill: theme.area,
        z: null,
      }),
    );
  }

  marks.push(
    ...lineDotMarks(data, {
      x: "date",
      y: "value",
      stroke: theme.primaryLine,
      dotRadius: 3,
      z: null,
    }),
  );

  if (regressionData.length > 0) {
    marks.push(
      Plot.dot(regressionData, {
        x: "date",
        y: "value",
        fill: theme.danger,
        r: 4,
      }),
    );
  }

  return marks;
}

type SeriesTrendRow = Readonly<{
  date: Date;
  value: number;
  series: string;
}>;

function buildDualSeriesTrendPlot(
  data: SeriesTrendRow[],
  theme: ChartTheme,
  options: Readonly<{
    width?: number;
    height?: number;
    targetMs?: number;
    yLabel?: string;
    legendDomain: string[];
    legendRange: string[];
  }>,
): Plot.PlotOptions {
  const width = options.width ?? 640;
  const height = options.height ?? 200;
  const marks: Plot.Markish[] = [];

  if (options.targetMs !== undefined) {
    marks.push(Plot.ruleY([options.targetMs], { stroke: theme.target, strokeDasharray: "4,4" }));
  }

  marks.push(
    ...lineDotMarks(data, {
      x: "date",
      y: "value",
      stroke: "series",
      fill: "series",
      z: "series",
    }),
  );

  return {
    width,
    height,
    marginLeft: 48,
    marginRight: options.legendDomain.length > 2 ? 48 : 16,
    marginTop: 16,
    marginBottom: 32,
    x: { type: "time", label: null },
    y: { label: options.yLabel ?? null, grid: true },
    color: {
      legend: true,
      domain: options.legendDomain,
      range: options.legendRange,
    },
    marks,
    style: plotMonoStyle(theme),
  };
}

export function buildTrendPlot(
  data: TrendDatum[],
  theme: ChartTheme,
  options?: {
    width?: number;
    height?: number;
    targetMs?: number;
    yLabel?: string;
    yTickFormat?: (value: number) => string;
    showCiBand?: boolean;
  },
): Plot.PlotOptions {
  const width = options?.width ?? 640;
  const height = options?.height ?? 200;
  const yTickFormat = options?.yTickFormat ?? ((value: number) => `${value}ms`);
  const showCiBand = options?.showCiBand ?? true;
  const marks = [
    ...trendAxisMarks(theme, yTickFormat),
    ...(options?.targetMs === undefined
      ? []
      : [
          Plot.ruleY([options.targetMs], {
            stroke: theme.target,
            strokeDasharray: "4,4",
            strokeWidth: 1,
          }),
        ]),
    ...trendSeriesMarks(data, theme, showCiBand),
    Plot.tip(
      data,
      Plot.pointer({
        x: "date",
        y: "value",
        title: (datum: TrendDatum) => formatTrendTipTitle(datum),
      }),
    ),
  ];

  return {
    width,
    height,
    marginLeft: 48,
    marginRight: 16,
    marginTop: 16,
    marginBottom: 32,
    x: { type: "time", label: null },
    y: { label: options?.yLabel ?? null, grid: false },
    marks,
    style: plotMonoStyle(theme),
  };
}

export function buildWaterfallPlot(
  stages: StageLatency,
  theme: ChartTheme,
  isDark: boolean,
  width = 640,
): Plot.PlotOptions {
  const stageKeys: StageKey[] = [
    "auth_lru_p99_ms",
    "auth_grpc_p99_ms",
    "rate_limit_p99_ms",
    "directive_resolve_p99_ms",
    "prompt_inject_p99_ms",
    "total_overhead_p99_ms",
  ];
  const rows = stageKeys.map((key) => ({
    stage: STAGE_LABELS[key],
    key,
    value: stages[key],
    color: stageColor(key, isDark),
  }));

  return {
    width,
    height: 220,
    marginLeft: 120,
    marginRight: 16,
    marginTop: 8,
    marginBottom: 8,
    x: { label: null, grid: true, tickFormat: (value: number) => `${value}ms` },
    y: { label: null },
    marks: [
      Plot.barX(rows, {
        y: "stage",
        x: "value",
        fill: "color",
        inset: 0.2,
      }),
      Plot.ruleX([0], { stroke: theme.grid }),
    ],
    style: plotMonoStyle(theme),
  };
}

export function buildPercentilePlot(
  run: BenchmarkRun,
  theme: ChartTheme,
  width = 640,
  targetMs = 20,
): Plot.PlotOptions {
  const rows = [
    { percentile: "p50", value: run.k6.p50_ms },
    { percentile: "p95", value: run.k6.p95_ms },
    { percentile: "p99", value: run.k6.p99_ms },
    { percentile: "p99.9", value: run.k6.p999_ms },
  ];

  return {
    width,
    height: 220,
    marginLeft: 72,
    marginRight: 24,
    marginTop: 8,
    marginBottom: 8,
    x: { label: null, grid: true, tickFormat: (value: number) => `${value}ms` },
    y: { label: null },
    color: {
      domain: ["p50", "p95", "p99", "p99.9"],
      range: [...theme.series],
    },
    marks: [
      Plot.barX(rows, {
        y: "percentile",
        x: "value",
        fill: "percentile",
        inset: 0.2,
      }),
      Plot.ruleX([targetMs], {
        stroke: theme.target,
        strokeDasharray: "4,4",
      }),
      Plot.ruleX([0], { stroke: theme.grid }),
    ],
    style: plotMonoStyle(theme),
  };
}

export function buildSeriesTrendPlot(
  data: SeriesTrendRow[],
  theme: ChartTheme,
  preset: SeriesTrendPreset,
  width = 640,
): Plot.PlotOptions {
  return buildDualSeriesTrendPlot(data, theme, {
    width,
    ...preset,
    legendRange: [...preset.legendRange],
  });
}

export function buildThroughputDurationPlot(
  data: ThroughputDurationDatum[],
  theme: ChartTheme,
  width = 640,
): Plot.PlotOptions {
  return {
    width,
    height: 200,
    marginLeft: 48,
    marginRight: 16,
    marginTop: 16,
    marginBottom: 32,
    x: { label: "Time (s)", grid: true, tickFormat: (value: number) => `${value}s` },
    y: { label: null, grid: true, tickFormat: (value: number) => `${Math.round(value)}` },
    marks: [
      ...lineDotMarks(data, {
        x: "t_s",
        y: "req_per_s",
        stroke: theme.primaryLine,
        z: null,
      }),
      Plot.ruleY([0], { stroke: theme.grid }),
    ],
    style: plotMonoStyle(theme),
  };
}

export function buildStageStackPlot(
  data: StageStackRow[],
  theme: ChartTheme,
  width = 640,
  targetMs = 20,
): Plot.PlotOptions {
  const stageDomain = [
    ...STACK_STAGE_KEYS.map((key) => STAGE_LABELS[key]),
    "Other overhead",
  ];
  const stageRange = [
    ...STACK_STAGE_KEYS.map((key) => stageColor(key, theme.isDark)),
    otherOverheadColor(theme.isDark),
  ];

  return {
    width,
    height: 220,
    marginLeft: 48,
    marginRight: 16,
    marginTop: 16,
    marginBottom: 32,
    x: { type: "time", label: null },
    y: { label: null, tickFormat: (value: number) => `${value}ms`, grid: true },
    color: { legend: true, domain: stageDomain, range: stageRange },
    marks: [
      Plot.ruleY([targetMs], { stroke: theme.target, strokeDasharray: "4,4" }),
      Plot.areaY(data, {
        x: "date",
        y: "value",
        fill: "stage",
        stroke: stageColor("auth_lru_p99_ms", theme.isDark),
        strokeOpacity: 0.35,
        order: null,
        z: "stage",
      }),
    ],
    style: plotMonoStyle(theme),
  };
}
