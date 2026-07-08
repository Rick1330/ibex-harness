import { Check, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { formatMs } from "@/lib/benchmarks/format";

type SlaGaugeProps = Readonly<{
  label: string;
  value: number;
  target: number;
  formatValue?: (value: number) => string;
}>;

function fillClass(ratio: number): string {
  if (ratio > 1) return "sla-fill-80";
  if (ratio >= 0.9) return "sla-fill-60";
  if (ratio >= 0.7) return "sla-fill-40";
  return "sla-fill-25";
}

export function SlaGauge({ label, value, target, formatValue = formatMs }: SlaGaugeProps) {
  const ratio = target > 0 ? value / target : 0;
  const displayPct = Math.round(ratio * 100);
  const barPct = Math.min(displayPct, 100);
  const passed = value <= target;
  const StatusIcon = passed ? Check : X;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-foreground">
          {formatValue(value)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex h-1.5 flex-1 items-center rounded-sm bg-muted">
          <progress
            aria-label={`${label} SLA usage`}
            aria-valuenow={displayPct}
            className={cn("sla-gauge-progress", fillClass(ratio))}
            max={100}
            value={barPct}
          />
        </div>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {displayPct}%
        </span>
        <span className="text-xs text-muted-foreground">target {formatValue(target)}</span>
        <span className="inline-flex text-muted-foreground" aria-label={passed ? "Passed" : "Failed"}>
          <StatusIcon className="h-4 w-4" strokeWidth={1.5} aria-hidden />
        </span>
      </div>
    </div>
  );
}
