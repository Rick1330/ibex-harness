import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from "lucide-react";

import { cn } from "@/lib/cn";
import { formatDeltaPct } from "@/lib/benchmarks/format";
import type { BenchmarkRun, RunStatus } from "@/lib/benchmarks/types";

type StatusBadgeProps = Readonly<{
  run: BenchmarkRun;
}>;

function statusConfig(status: RunStatus) {
  switch (status) {
    case "pass":
      return {
        icon: CheckCircle2,
        label: "PASSING",
        container: "border-border bg-card",
        accent: "text-success",
        dot: "bg-success",
      };
    case "regression":
      return {
        icon: AlertTriangle,
        label: "REGRESSION",
        container: "border-warning/30 bg-warning/5",
        accent: "text-warning",
        dot: "bg-warning",
      };
    case "fail":
      return {
        icon: XCircle,
        label: "FAILING",
        container: "border-danger/30 bg-danger/5",
        accent: "text-danger",
        dot: "bg-danger",
      };
    default:
      return {
        icon: HelpCircle,
        label: "UNKNOWN",
        container: "border-border bg-card",
        accent: "text-muted-foreground",
        dot: "bg-muted-foreground",
      };
  }
}

function formatTimestamp(value: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toUTCString();
}

export function BenchmarkStatusBadge({ run }: StatusBadgeProps) {
  const config = statusConfig(run.status);
  const Icon = config.icon;
  const regression = formatDeltaPct(run.regression_vs_baseline_pct);

  return (
    <div className={cn("rounded-md border p-4", config.container)}>
      <div className="flex items-center gap-2">
        <span className={cn("inline-block h-2 w-2 rounded-full", config.dot)} />
        <Icon className={cn("h-4 w-4", config.accent)} aria-hidden />
        <span className={cn("font-mono text-sm font-semibold", config.accent)}>
          {config.label}
        </span>
        {typeof run.regression_vs_baseline_pct === "number" && (
          <span className="font-mono text-xs text-muted-foreground">
            {regression} vs baseline
          </span>
        )}
      </div>
      <p className="mt-2 font-mono text-xs text-muted-foreground">
        Run #{run.run_number || "—"} · {run.short_sha} · {run.branch} · {formatTimestamp(run.timestamp)}
      </p>
      <p className="mt-1 font-mono text-xs text-muted-foreground">
        {run.runner_os} · Go {run.go_version || "—"} · {run.runner_cpu} · {run.runner_vcpus} vCPU ·{" "}
        {run.runner_ram_gb} GB RAM
      </p>
    </div>
  );
}
