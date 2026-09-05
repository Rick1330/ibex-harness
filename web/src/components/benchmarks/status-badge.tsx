import { formatDeltaPct } from "@/lib/benchmarks/format";
import type { BenchmarkRun } from "@/lib/benchmarks/types";

import { SuiteStatusBadge } from "@/components/benchmarks/suite-status-badge";

type StatusBadgeProps = Readonly<{
  run: BenchmarkRun;
}>;

function formatUtcTimestamp(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toUTCString();
}

export function BenchmarkStatusBadge({ run }: StatusBadgeProps) {
  const regression = formatDeltaPct(run.regression_vs_baseline_pct);
  const deltaLabel =
    typeof run.regression_vs_baseline_pct === "number"
      ? `${regression} vs baseline`
      : null;

  return (
    <SuiteStatusBadge
      status={run.status}
      runNumber={run.run_number || "—"}
      shortSha={run.short_sha}
      branch={run.branch}
      timestamp={formatUtcTimestamp(run.timestamp)}
      deltaLabel={deltaLabel}
      detail={
        <p className="font-mono">
          {run.runner_os} · Go {run.go_version || "—"} · {run.runner_cpu} · {run.runner_vcpus}{" "}
          vCPU · {run.runner_ram_gb} GB RAM
        </p>
      }
    />
  );
}
