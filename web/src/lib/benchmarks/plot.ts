import { STAGE_LABELS } from "@/lib/benchmarks/chart-colors";
import { proxyOverheadBenchmark } from "@/lib/benchmarks/run-benchmarks";
import type { BenchmarkRun, RunStatus } from "@/lib/benchmarks/types";

export type TimeRange = "7d" | "14d" | "30d" | "90d" | "all";

const RANGE_DAYS: Record<Exclude<TimeRange, "all">, number> = {
  "7d": 7,
  "14d": 14,
  "30d": 30,
  "90d": 90,
};

export function runDate(run: BenchmarkRun): Date {
  return new Date(run.timestamp);
}

function filterRunsSinceCutoff(runs: BenchmarkRun[], days: number): BenchmarkRun[] {
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return runs.filter((run) => runDate(run).getTime() >= cutoff);
}

export function sortRunsByDate(runs: BenchmarkRun[]): BenchmarkRun[] {
  return [...runs].sort((a, b) => runDate(a).getTime() - runDate(b).getTime());
}

const VALID_TIME_RANGES = new Set<TimeRange>(["7d", "14d", "30d", "90d", "all"]);

export function parseTimeRange(value: string | null, fallback: TimeRange = "14d"): TimeRange {
  if (value && VALID_TIME_RANGES.has(value as TimeRange)) {
    return value as TimeRange;
  }
  return fallback;
}

export function filterRunsByRange(runs: BenchmarkRun[], range: TimeRange): BenchmarkRun[] {
  if (range === "all" || runs.length === 0) {
    return runs;
  }

  return filterRunsSinceCutoff(runs, RANGE_DAYS[range]);
}

export function filterRunsByDays(runs: BenchmarkRun[], days: number): BenchmarkRun[] {
  if (days <= 0 || runs.length === 0) {
    return runs;
  }
  return filterRunsSinceCutoff(runs, days);
}

export interface TrendDatum {
  date: Date;
  value: number;
  status: RunStatus;
  shortSha: string;
  ciLow?: number;
  ciHigh?: number;
  timestamp?: string;
  prLabel?: string;
  deltaPct?: number | null;
  budgetPct?: number | null;
  runner?: string;
}

export function toTrendData(
  runs: BenchmarkRun[],
  metric: (run: BenchmarkRun) => number,
  ci?: (run: BenchmarkRun) => { low: number; high: number } | null,
  targetMs?: number,
): TrendDatum[] {
  return sortRunsByDate(runs).map((run) => {
      const band = ci?.(run);
      const value = metric(run);
      return {
        date: runDate(run),
        value,
        status: run.status,
        shortSha: run.short_sha,
        ciLow: band?.low,
        ciHigh: band?.high,
        timestamp: run.timestamp,
        prLabel: run.pr_number ? `PR #${run.pr_number}` : run.branch,
        deltaPct: run.regression_vs_baseline_pct,
        budgetPct:
          targetMs && targetMs > 0 ? (value / targetMs) * 100 : undefined,
        runner: `Go ${run.go_version || "—"} · ${run.runner_os} · ${run.runner_vcpus} vCPU`,
      };
    });
}

export interface PercentileSeriesRow {
  date: Date;
  series: string;
  value: number;
}

export function toPercentileTrendData(runs: BenchmarkRun[]): PercentileSeriesRow[] {
  const rows: PercentileSeriesRow[] = [];
  for (const run of sortRunsByDate(runs)) {
    const date = runDate(run);
    rows.push(
      { date, series: "p50", value: run.k6.p50_ms },
      { date, series: "p95", value: run.k6.p95_ms },
      { date, series: "p99", value: run.k6.p99_ms },
      { date, series: "p99.9", value: run.k6.p999_ms },
    );
  }
  return rows;
}

export interface AllocSeriesRow {
  date: Date;
  series: string;
  value: number;
}

export function toAllocTrendData(runs: BenchmarkRun[]): AllocSeriesRow[] {
  const rows: AllocSeriesRow[] = [];
  for (const run of sortRunsByDate(runs)) {
    const bench = proxyOverheadBenchmark(run);
    if (!bench) {
      continue;
    }
    const date = runDate(run);
    rows.push(
      { date, series: "bytes/op", value: bench.bytes_per_op / 1024 },
      { date, series: "allocs/op", value: bench.allocs_per_op },
    );
  }
  return rows;
}

const STACK_STAGE_KEYS = [
  "auth_lru_p99_ms",
  "auth_grpc_p99_ms",
  "rate_limit_p99_ms",
  "directive_resolve_p99_ms",
  "prompt_inject_p99_ms",
] as const;

export interface StageStackRow {
  date: Date;
  stage: string;
  value: number;
}

export function toStageStackData(runs: BenchmarkRun[]): StageStackRow[] {
  const rows: StageStackRow[] = [];
  for (const run of sortRunsByDate(runs)) {
    const date = runDate(run);
    for (const key of STACK_STAGE_KEYS) {
      rows.push({
        date,
        stage: STAGE_LABELS[key],
        value: run.stages[key],
      });
    }
    const summed = STACK_STAGE_KEYS.reduce((total, key) => total + run.stages[key], 0);
    const other = Math.max(run.stages.total_overhead_p99_ms - summed, 0);
    rows.push({ date, stage: "Other overhead", value: other });
  }
  return rows;
}

export interface ThroughputDurationDatum {
  t_s: number;
  req_per_s: number;
}
