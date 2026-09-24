"use client"

import { IconArrowDownRight, IconArrowUpRight } from "@tabler/icons-react"

import { cn } from "@/lib/utils"

export function KpiCard({
  label,
  value,
  deltaPct,
  higherIsBetter = true,
  hint,
  partial,
  mutedValue,
}: {
  label: string
  value: string
  deltaPct?: number
  higherIsBetter?: boolean
  hint?: string
  /** ClickHouse completeness != complete for this field's buckets. */
  partial?: boolean
  /** Soften visual weight (e.g. estimated cost vs reconciled). */
  mutedValue?: boolean
}) {
  return (
    <div className="rounded-lg border border-border/70 bg-card px-4 py-3 shadow-[0_1px_2px_oklch(0_0_0/0.04)] dark:shadow-none">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          {label}
        </div>
        {partial ? (
          <span
            className="shrink-0 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-400"
            title="Underlying ClickHouse buckets include completeness=partial rows"
          >
            partial data
          </span>
        ) : null}
      </div>
      <div
        className={cn(
          "mt-1.5 font-mono text-[22px] font-medium tracking-tight tabular-nums",
          mutedValue ? "text-muted-foreground" : "text-foreground",
        )}
      >
        {value}
      </div>
      <div className="mt-1.5 flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {deltaPct != null ? (
          <TrendDelta value={deltaPct} higherIsBetter={higherIsBetter} />
        ) : null}
        {hint ? <span>{hint}</span> : null}
      </div>
    </div>
  )
}

export function TrendDelta({
  value,
  higherIsBetter,
}: {
  value: number
  higherIsBetter: boolean
}) {
  const good = higherIsBetter ? value >= 0 : value <= 0
  return (
    <span
      className={cn(
        "inline-flex items-center gap-0.5 font-mono tabular-nums",
        good ? "text-foreground" : "text-destructive",
      )}
    >
      {value >= 0 ? (
        <IconArrowUpRight className="size-3" aria-hidden />
      ) : (
        <IconArrowDownRight className="size-3" aria-hidden />
      )}
      {value >= 0 ? "+" : ""}
      {value.toFixed(1)}%
    </span>
  )
}
