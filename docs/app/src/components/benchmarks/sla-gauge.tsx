import { cn } from "@/lib/cn";
import { formatMs } from "@/lib/benchmarks/format";

type SlaGaugeProps = Readonly<{
  label: string;
  valueMs: number;
  targetMs: number;
}>;

function fillClass(ratio: number): string {
  if (ratio > 1) return "bg-danger";
  if (ratio >= 0.9) return "bg-danger/70";
  if (ratio >= 0.7) return "bg-warning/70";
  return "bg-success/70";
}

export function SlaGauge({ label, valueMs, targetMs }: SlaGaugeProps) {
  const ratio = targetMs > 0 ? valueMs / targetMs : 0;
  const widthPct = Math.min(ratio * 100, 100);
  const passed = valueMs <= targetMs;

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className="font-mono text-sm font-semibold tabular-nums text-foreground">
          {formatMs(valueMs)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <div className="h-1.5 flex-1 rounded-full bg-muted">
          <div
            className={cn("h-1.5 rounded-full transition-[width] duration-500", fillClass(ratio))}
            style={{ width: `${widthPct}%` }}
          />
        </div>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          {Math.round(ratio * 100)}%
        </span>
        <span className="text-xs text-muted-foreground">target {formatMs(targetMs)}</span>
        <span className={cn("text-xs", passed ? "text-success" : "text-danger")}>
          {passed ? "✓" : "✗"}
        </span>
      </div>
    </div>
  );
}
