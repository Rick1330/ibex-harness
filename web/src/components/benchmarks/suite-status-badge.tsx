import { cn } from "@/lib/cn";
import type { ReactNode } from "react";

import { runStatusVisualConfig } from "@/lib/benchmarks/run-status-config";
import type { RunStatus } from "@/lib/benchmarks/types";

type SuiteStatusBadgeProps = Readonly<{
  status: RunStatus;
  runNumber: number | string;
  shortSha: string;
  branch?: string;
  timestamp?: string;
  detail?: ReactNode;
  deltaLabel?: string | null;
}>;

export function SuiteStatusBadge({
  status,
  runNumber,
  shortSha,
  branch,
  timestamp,
  detail,
  deltaLabel,
}: SuiteStatusBadgeProps) {
  const config = runStatusVisualConfig(status);
  const Icon = config.icon;

  return (
    <div className={cn("rounded-md border p-4", config.container)}>
      <div className="flex flex-wrap items-center gap-2">
        <span className={cn("inline-block h-2 w-2 rounded-full", config.dot)} />
        <Icon className={cn("h-4 w-4", config.accent)} aria-hidden />
        <span className={cn("font-mono text-sm font-semibold", config.accent)}>
          {config.label}
        </span>
        {deltaLabel ? (
          <span className="font-mono text-xs text-muted-foreground">{deltaLabel}</span>
        ) : null}
      </div>
      <p className="mt-2 font-mono text-xs text-muted-foreground">
        Run #{runNumber} · {shortSha}
        {branch ? ` · ${branch}` : ""}
        {timestamp ? ` · ${timestamp}` : ""}
      </p>
      {detail ? <div className="mt-1 text-xs text-muted-foreground">{detail}</div> : null}
    </div>
  );
}
