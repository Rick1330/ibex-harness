import { AlertTriangle } from "lucide-react";

import type { BenchmarkRun } from "@/lib/benchmarks/types";
import { formatDeltaPct, formatMs } from "@/lib/benchmarks/format";

type RegressionAlertProps = Readonly<{
  run: BenchmarkRun;
  baselineP99Ms?: number;
  runs?: BenchmarkRun[];
}>;

function findRevertRun(runs: BenchmarkRun[], regressionRun: BenchmarkRun): BenchmarkRun | null {
  const sorted = [...runs].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime(),
  );
  const index = sorted.findIndex((entry) => entry.sha === regressionRun.sha);
  if (index === -1) {
    return null;
  }

  for (const candidate of sorted.slice(index + 1)) {
    if (candidate.status === "pass" || candidate.status === "unknown") {
      return candidate;
    }
  }

  return null;
}

export function RegressionAlert({ run, baselineP99Ms, runs }: RegressionAlertProps) {
  if (run.status !== "regression") {
    return null;
  }

  const delta = formatDeltaPct(run.regression_vs_baseline_pct);
  const current = formatMs(run.k6.p99_ms);
  const baseline = baselineP99Ms ? formatMs(baselineP99Ms) : "baseline";
  const revert = runs ? findRevertRun(runs, run) : null;

  return (
    <div className="rounded-md border border-warning/30 bg-warning/5 p-4">
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
        <div>
          <p className="font-mono text-sm font-semibold text-warning">Regression detected</p>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            Run {run.short_sha}: p99 {current} ({delta} vs {baseline})
          </p>
          {revert ? (
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              Reverted in {revert.short_sha} on{" "}
              {new Date(revert.timestamp).toLocaleDateString("en-US", { timeZone: "UTC" })}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  );
}
