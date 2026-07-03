"use client";

import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { BenchmarkEmptyState } from "@/components/benchmarks/empty-state";
import { BenchmarkErrorState } from "@/components/benchmarks/benchmark-error-state";
import { ChartSkeleton } from "@/components/benchmarks/skeleton";
import { cn } from "@/lib/cn";
import { formatDeltaPct, formatMs, formatPercent, formatReqPerSec } from "@/lib/benchmarks/format";
import { pctChange } from "@/lib/benchmarks/regression";
import { findRunBySha } from "@/lib/benchmarks/runs";
import { useBenchmarkData } from "@/hooks/use-benchmark-data";

const COMPARE_SELECT_CLASS =
  "w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-sm focus:border-border-strong focus:outline-none focus:ring-2 focus:ring-border-strong/40";

type MetricRow = Readonly<{
  label: string;
  base: string;
  head: string;
  delta: string;
  deltaValue: number | null;
  higherIsBetter?: boolean;
}>;

function deltaClass(delta: number | null, higherIsBetter = false): string {
  if (delta === null || !Number.isFinite(delta) || Math.abs(delta) < 0.05) {
    return "text-muted-foreground";
  }
  const improved = higherIsBetter ? delta > 0 : delta < 0;
  return improved ? "text-success" : "text-danger";
}

function CompareContent() {
  const { runs, isLoading, isError, error } = useBenchmarkData();
  const router = useRouter();
  const searchParams = useSearchParams();
  const baseSha = searchParams.get("base") ?? "";
  const headSha = searchParams.get("head") ?? "";

  if (isLoading) {
    return <ChartSkeleton className="h-[200px]" />;
  }

  if (isError) {
    return (
      <BenchmarkErrorState
        message={error instanceof Error ? error.message : "Failed to load benchmark data"}
      />
    );
  }

  if (runs.length === 0) {
    return <BenchmarkEmptyState />;
  }

  const baseRun = baseSha ? findRunBySha(runs, baseSha) : runs[1] ?? runs[0];
  const headRun = headSha ? findRunBySha(runs, headSha) : runs[0];

  if (!baseRun || !headRun) {
    return <BenchmarkEmptyState />;
  }

  const rows: MetricRow[] = [
    {
      label: "Proxy p99",
      base: formatMs(baseRun.k6.p99_ms),
      head: formatMs(headRun.k6.p99_ms),
      delta: formatDeltaPct(pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms)),
      deltaValue: pctChange(baseRun.k6.p99_ms, headRun.k6.p99_ms),
    },
    {
      label: "Throughput",
      base: formatReqPerSec(baseRun.k6.req_per_s),
      head: formatReqPerSec(headRun.k6.req_per_s),
      delta: formatDeltaPct(pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true)),
      deltaValue: pctChange(baseRun.k6.req_per_s, headRun.k6.req_per_s, true),
      higherIsBetter: true,
    },
    {
      label: "Error rate",
      base: formatPercent(baseRun.k6.error_rate),
      head: formatPercent(headRun.k6.error_rate),
      delta: formatDeltaPct(pctChange(baseRun.k6.error_rate, headRun.k6.error_rate)),
      deltaValue: pctChange(baseRun.k6.error_rate, headRun.k6.error_rate),
    },
    {
      label: "Total overhead p99",
      base: formatMs(baseRun.stages.total_overhead_p99_ms),
      head: formatMs(headRun.stages.total_overhead_p99_ms),
      delta: formatDeltaPct(
        pctChange(baseRun.stages.total_overhead_p99_ms, headRun.stages.total_overhead_p99_ms),
      ),
      deltaValue: pctChange(baseRun.stages.total_overhead_p99_ms, headRun.stages.total_overhead_p99_ms),
    },
  ];

  function updateParam(key: "base" | "head", value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set(key, value);
    router.replace(`/benchmarks/compare?${params.toString()}`);
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-2">
        <label className="space-y-1 text-sm">
          <span className="text-muted-foreground">Base</span>
          <select
            value={baseRun.short_sha}
            onChange={(event) => updateParam("base", event.target.value)}
            className={COMPARE_SELECT_CLASS}
          >
            {runs.map((run) => (
              <option key={run.sha} value={run.short_sha}>
                {run.short_sha} · {run.branch}
              </option>
            ))}
          </select>
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-muted-foreground">Head</span>
          <select
            value={headRun.short_sha}
            onChange={(event) => updateParam("head", event.target.value)}
            className={COMPARE_SELECT_CLASS}
          >
            {runs.map((run) => (
              <option key={run.sha} value={run.short_sha}>
                {run.short_sha} · {run.branch}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-border bg-muted/40">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Metric
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                {baseRun.short_sha}
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                {headRun.short_sha}
              </th>
              <th scope="col" className="px-4 py-3 font-medium text-muted-foreground">
                Delta
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label} className="history-row border-b border-border/70 last:border-0">
                <td className="px-4 py-3">{row.label}</td>
                <td className="px-4 py-3 font-mono tabular-nums">{row.base}</td>
                <td className="px-4 py-3 font-mono tabular-nums">{row.head}</td>
                <td
                  className={cn(
                    "px-4 py-3 font-mono tabular-nums",
                    deltaClass(row.deltaValue, row.higherIsBetter),
                  )}
                >
                  {row.delta}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function BenchmarkComparePanel() {
  return (
    <Suspense fallback={<ChartSkeleton className="h-[200px]" />}>
      <CompareContent />
    </Suspense>
  );
}
