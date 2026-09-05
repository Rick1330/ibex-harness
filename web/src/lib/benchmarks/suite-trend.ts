import type { TrendDatum } from "@/lib/benchmarks/plot";
import type { RunStatus } from "@/lib/benchmarks/types";

export type SuiteRunIdentity = Readonly<{
  timestamp: string;
  short_sha: string;
  branch?: string;
  status?: string | null;
}>;

const KNOWN_RUN_STATUSES = new Set<RunStatus>([
  "pass",
  "fail",
  "regression",
  "unknown",
]);

/** Normalize published suite status strings (incl. HNSW `warn`) to RunStatus. */
export function toRunStatus(raw: string | null | undefined): RunStatus {
  if (raw != null && KNOWN_RUN_STATUSES.has(raw as RunStatus)) {
    return raw as RunStatus;
  }
  return "unknown";
}

export function filterSuiteRunsByRange<T extends SuiteRunIdentity>(
  runs: readonly T[],
  range: "7d" | "14d" | "30d" | "90d" | "all",
): T[] {
  if (range === "all" || runs.length === 0) {
    return [...runs];
  }
  const days = { "7d": 7, "14d": 14, "30d": 30, "90d": 90 }[range];
  const cutoff = Date.now() - days * 24 * 60 * 60 * 1000;
  return runs.filter((run) => new Date(run.timestamp).getTime() >= cutoff);
}

export function suiteRunsToTrendData<T extends SuiteRunIdentity>(
  runs: readonly T[],
  metric: (run: T) => number | null,
  targetMs?: number,
): TrendDatum[] {
  return [...runs]
    .flatMap((run) => {
      const value = metric(run);
      if (value == null || !Number.isFinite(value)) {
        return [];
      }
      const row: TrendDatum = {
        date: new Date(run.timestamp),
        value,
        status: toRunStatus(run.status),
        shortSha: run.short_sha,
        timestamp: run.timestamp,
        prLabel: run.branch,
        budgetPct: targetMs && targetMs > 0 ? (value / targetMs) * 100 : undefined,
      };
      return [row];
    })
    .sort((a, b) => a.date.getTime() - b.date.getTime());
}

/** Delta percent of current vs previous (previous is older; runs newest-first). */
export function deltaPctVsPrevious(
  current: number,
  previous: number | null | undefined,
): number | null {
  if (previous == null || !Number.isFinite(previous)) {
    return null;
  }
  if (previous === 0) {
    return null;
  }
  return ((current - previous) / Math.abs(previous)) * 100;
}
