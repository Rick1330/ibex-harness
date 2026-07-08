import type { BenchmarkRun, RunStatus } from "@/lib/benchmarks/types";

export type HistorySortKey =
  | "run_number"
  | "short_sha"
  | "branch"
  | "status"
  | "p99"
  | "req_per_s"
  | "delta"
  | "timestamp";

export type HistorySortDir = "asc" | "desc";

const STATUS_ORDER: Record<RunStatus, number> = {
  fail: 0,
  regression: 1,
  unknown: 2,
  pass: 3,
};

type HistoryMetricsSortKey = "p99" | "req_per_s" | "delta" | "timestamp";
type HistoryMetaSortKey = Exclude<HistorySortKey, HistoryMetricsSortKey>;

const METRICS_SORT_KEYS = new Set<HistorySortKey>([
  "p99",
  "req_per_s",
  "delta",
  "timestamp",
]);

function isMetricsSortKey(key: HistorySortKey): key is HistoryMetricsSortKey {
  return METRICS_SORT_KEYS.has(key);
}

function sortValueMeta(run: BenchmarkRun, key: HistoryMetaSortKey): string | number {
  switch (key) {
    case "run_number":
      return run.run_number;
    case "short_sha":
      return run.short_sha;
    case "branch":
      return run.branch;
    case "status":
      return STATUS_ORDER[run.status];
  }
}

function sortValueMetrics(run: BenchmarkRun, key: HistoryMetricsSortKey): string | number {
  switch (key) {
    case "p99":
      return run.k6.p99_ms;
    case "req_per_s":
      return run.k6.req_per_s;
    case "delta":
      return run.regression_vs_baseline_pct ?? Number.NEGATIVE_INFINITY;
    case "timestamp":
      return new Date(run.timestamp).getTime();
  }
}

function sortValue(run: BenchmarkRun, key: HistorySortKey): string | number {
  if (isMetricsSortKey(key)) {
    return sortValueMetrics(run, key);
  }
  return sortValueMeta(run, key);
}

export function compareHistoryRuns(
  a: BenchmarkRun,
  b: BenchmarkRun,
  key: HistorySortKey,
  dir: HistorySortDir,
): number {
  const left = sortValue(a, key);
  const right = sortValue(b, key);
  const cmp =
    typeof left === "string" && typeof right === "string"
      ? left.localeCompare(right)
      : Number(left) - Number(right);
  return dir === "asc" ? cmp : -cmp;
}

export function statusClassName(status: RunStatus): string {
  switch (status) {
    case "pass":
      return "text-success";
    case "regression":
      return "text-warning";
    case "fail":
      return "text-danger";
    default:
      return "text-muted-foreground";
  }
}

export function sortIndicator(active: boolean, sortDir: HistorySortDir): string {
  if (!active) {
    return "";
  }
  if (sortDir === "asc") {
    return " ↑";
  }
  return " ↓";
}

export function defaultSortDirForKey(key: HistorySortKey): HistorySortDir {
  return key === "timestamp" ? "desc" : "asc";
}
