"use client";

import dynamic from "next/dynamic";

import { ChartSkeleton } from "@/components/benchmarks/skeleton";

const panelLoading = (height: string) =>
  function PanelLoading() {
    return <ChartSkeleton className={height} />;
  };

export const BenchmarkOverviewPanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-overview-panel").then(
      (mod) => mod.BenchmarkOverviewPanel,
    ),
  { loading: panelLoading("h-96"), ssr: false },
);

export const BenchmarkLatencyPanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-latency-panel").then(
      (mod) => mod.BenchmarkLatencyPanel,
    ),
  { loading: panelLoading("h-96"), ssr: false },
);

export const BenchmarkWaterfallPanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-waterfall-panel").then(
      (mod) => mod.BenchmarkWaterfallPanel,
    ),
  { loading: panelLoading("h-[220px]"), ssr: false },
);

export const BenchmarkLoadPanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-load-panel").then((mod) => mod.BenchmarkLoadPanel),
  { loading: panelLoading("h-96"), ssr: false },
);

export const BenchmarkHistoryPanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-history-panel").then(
      (mod) => mod.BenchmarkHistoryPanel,
    ),
  { loading: panelLoading("h-[200px]"), ssr: false },
);

export const BenchmarkComparePanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-compare-panel").then(
      (mod) => mod.BenchmarkComparePanel,
    ),
  { loading: panelLoading("h-64"), ssr: false },
);

export const BenchmarkRunDetailPanel = dynamic(
  () =>
    import("@/components/benchmarks/benchmark-run-detail-panel").then(
      (mod) => mod.BenchmarkRunDetailPanel,
    ),
  { loading: panelLoading("h-96"), ssr: false },
);
