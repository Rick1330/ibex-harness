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

const SORT_ACCESSORS: Record<HistorySortKey, (run: BenchmarkRun) => string | number> = {
  run_number: (run) => run.run_number,
  short_sha: (run) => run.short_sha,
  branch: (run) => run.branch,
  status: (run) => STATUS_ORDER[run.status],
  p99: (run) => run.k6.p99_ms,
  req_per_s: (run) => run.k6.req_per_s,
  delta: (run) => run.regression_vs_baseline_pct ?? Number.NEGATIVE_INFINITY,
  timestamp: (run) => new Date(run.timestamp).getTime(),
};

function sortValue(run: BenchmarkRun, key: HistorySortKey): string | number {
  return SORT_ACCESSORS[key](run);
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
