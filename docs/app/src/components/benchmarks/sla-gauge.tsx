import { Check, X } from "lucide-react";

import { cn } from "@/lib/cn";
import { formatMs } from "@/lib/benchmarks/format";

type SlaGaugeProps = Readonly<{
  label: string;
  valueMs: number;
  targetMs: number;
}>;

function fillClass(ratio: number): string {
  if (ratio > 1) return "bg-foreground/80";
  if (ratio >= 0.9) return "bg-foreground/60";
  if (ratio >= 0.7) return "bg-foreground/40";
  return "bg-foreground/25";
}

export function SlaGauge({ label, valueMs, targetMs }: SlaGaugeProps) {
  const ratio = targetMs > 0 ? valueMs / targetMs : 0;
  const widthPct = Math.min(ratio * 100, 100);
  const passed = valueMs <= targetMs;
  const StatusIcon = passed ? Check : X;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-foreground">
          {formatMs(valueMs)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="h-1.5 flex-1 rounded-sm bg-muted">
          <div
            role="progressbar"
            aria-label={`${label} SLA usage`}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(widthPct)}
            className={cn(
              "sla-bar-fill h-1.5 rounded-sm transition-[width] duration-150 ease-out",
              fillClass(ratio),
            )}
            style={{ width: `${widthPct}%` }}
          />
        </div>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {Math.round(ratio * 100)}%
        </span>
        <span className="text-xs text-muted-foreground">target {formatMs(targetMs)}</span>
        <span className={cn("inline-flex", passed ? "text-success" : "text-danger")}>
          <StatusIcon className="h-4 w-4" strokeWidth={1.5} aria-hidden />
        </span>
      </div>
    </div>
  );
}
