"use client";

import dynamic from "next/dynamic";

import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

const TrendChartImpl = dynamic(
  () => import("./trend-chart-impl").then((mod) => mod.TrendChartImpl),
  {
    ssr: false,
    loading: () => <ChartSkeleton className="h-[200px]" />,
  },
);

type TrendChartProps = Readonly<{
  runs: BenchmarkRun[];
  metric?: (run: BenchmarkRun) => number;
  targetMs?: number;
  height?: number;
  yTickFormat?: (value: number) => string;
  showCiBand?: boolean;
}>;

export function TrendChart(props: TrendChartProps) {
  return <TrendChartImpl {...props} />;
}
