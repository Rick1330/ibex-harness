import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";

import { cn } from "@/lib/cn";
import { formatDeltaPct } from "@/lib/benchmarks/format";

type KpiCardProps = Readonly<{
  label: string;
  value: string;
  deltaPct?: number | null;
  higherIsBetter?: boolean;
}>;

function trendMeta(deltaPct: number | null | undefined, higherIsBetter: boolean) {
  if (deltaPct === null || deltaPct === undefined || !Number.isFinite(deltaPct)) {
    return { icon: ArrowRight, className: "text-muted-foreground" };
  }
  if (Math.abs(deltaPct) < 0.05) {
    return { icon: ArrowRight, className: "text-muted-foreground" };
  }
  const improved = higherIsBetter ? deltaPct > 0 : deltaPct < 0;
  const TrendIcon = improved
    ? higherIsBetter
      ? ArrowUp
      : ArrowDown
    : higherIsBetter
      ? ArrowDown
      : ArrowUp;
  return {
    icon: TrendIcon,
    className: improved ? "text-success" : "text-danger",
  };
}

export function KpiCard({
  label,
  value,
  deltaPct = null,
  higherIsBetter = false,
}: KpiCardProps) {
  const trend = trendMeta(deltaPct, higherIsBetter);
  const TrendIcon = trend.icon;

  return (
    <article className="rounded-md border border-border bg-card p-5 transition-shadow duration-150 ease-out hover:shadow-[0_4px_12px_rgb(0_0_0/0.08)]">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 font-mono text-3xl font-semibold tabular-nums text-foreground">
        {value}
      </p>
      {deltaPct !== null && deltaPct !== undefined ? (
        <p className={cn("mt-2 flex items-center gap-1 font-mono text-xs", trend.className)}>
          <TrendIcon className="h-3.5 w-3.5" aria-hidden />
          {formatDeltaPct(deltaPct)} vs baseline
        </p>
      ) : null}
    </article>
  );
}
