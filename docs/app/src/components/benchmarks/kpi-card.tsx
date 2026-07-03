import type { LucideIcon } from "lucide-react";
import { ArrowDown, ArrowRight, ArrowUp } from "lucide-react";

import { cn } from "@/lib/cn";
import { formatDeltaPct } from "@/lib/benchmarks/format";

type KpiCardProps = Readonly<{
  label: string;
  value: string;
  deltaPct?: number | null;
  higherIsBetter?: boolean;
  hint?: string;
}>;

function trendMeta(deltaPct: number | null | undefined, higherIsBetter: boolean) {
  if (deltaPct === null || deltaPct === undefined) {
    return { icon: ArrowRight, className: "text-muted-foreground" };
  }
  if (!Number.isFinite(deltaPct)) {
    return { icon: ArrowRight, className: "text-muted-foreground" };
  }
  if (Math.abs(deltaPct) < 0.05) {
    return { icon: ArrowRight, className: "text-muted-foreground" };
  }
  const improved = higherIsBetter ? deltaPct > 0 : deltaPct < 0;
  const icon = deltaPct > 0 ? ArrowUp : ArrowDown;
  return {
    icon,
    className: improved ? "text-success" : "text-danger",
  };
}

function KpiFooter({
  showDelta,
  deltaPct,
  trendClassName,
  TrendIcon,
  hint,
}: Readonly<{
  showDelta: boolean;
  deltaPct: number | null | undefined;
  trendClassName: string;
  TrendIcon: LucideIcon;
  hint?: string;
}>) {
  if (showDelta) {
    return (
      <p className={cn("mt-2 flex items-center gap-1 font-mono text-xs", trendClassName)}>
        <TrendIcon className="h-4 w-4" strokeWidth={1.5} aria-hidden />
        {formatDeltaPct(deltaPct ?? null)} vs baseline
      </p>
    );
  }

  if (hint) {
    return <p className="mt-2 font-mono text-xs text-muted-foreground">{hint}</p>;
  }

  return null;
}

export function KpiCard({
  label,
  value,
  deltaPct = null,
  higherIsBetter = false,
  hint,
}: KpiCardProps) {
  const trend = trendMeta(deltaPct, higherIsBetter);
  const TrendIcon = trend.icon;
  const showDelta = deltaPct != null;

  return (
    <section
      aria-label={label}
      className="rounded-md border border-border bg-card p-5 transition-shadow duration-150 ease-out hover:shadow-[0_4px_12px_rgb(0_0_0/0.08)]"
    >
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 font-mono text-3xl font-semibold tabular-nums text-foreground">
        {value}
      </p>
      <KpiFooter
        showDelta={showDelta}
        deltaPct={deltaPct}
        trendClassName={trend.className}
        TrendIcon={TrendIcon}
        hint={hint}
      />
    </section>
  );
}
