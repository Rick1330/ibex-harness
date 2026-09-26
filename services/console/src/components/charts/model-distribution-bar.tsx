"use client"

import { cn } from "@/lib/utils"

const SEGMENT = [
  "bg-foreground",
  "bg-foreground/70",
  "bg-foreground/50",
  "bg-foreground/35",
  "bg-foreground/25",
  "bg-muted-foreground/50",
]

const TOP_N = 5

/**
 * model_distribution percentage map → horizontal stacked bar.
 * Caps at top N + Other — API does not paginate this field.
 */
export function ModelDistributionBar({
  distribution,
  className,
}: {
  distribution: Record<string, number>
  className?: string
}) {
  const entries = Object.entries(distribution).sort((a, b) => b[1] - a[1])
  if (!entries.length) {
    return <p className="text-[12px] text-muted-foreground">No model traffic</p>
  }

  const top = entries.slice(0, TOP_N)
  const rest = entries.slice(TOP_N)
  const otherShare = rest.reduce((s, [, v]) => s + v, 0)
  const segments = [
    ...top.map(([model, share], i) => ({
      model,
      share,
      className: SEGMENT[i % SEGMENT.length],
    })),
    ...(otherShare > 0
      ? [
          {
            model: `Other (${rest.length})`,
            share: otherShare,
            className: "bg-muted-foreground/30",
          },
        ]
      : []),
  ]

  return (
    <div className={cn("space-y-3", className)}>
      <div className="rounded-md border border-border bg-card px-3 py-3 shadow-[0_1px_2px_oklch(0_0_0/0.04)] dark:shadow-none">
        <div className="mb-2 text-[11px] font-medium text-muted-foreground">
          share of requests
        </div>
        <div className="flex h-2.5 w-full overflow-hidden rounded-sm bg-muted">
          {segments.map((s) => (
            <div
              key={s.model}
              className={cn("h-full min-w-[2px]", s.className)}
              style={{ width: `${s.share * 100}%` }}
              title={`${s.model} ${(s.share * 100).toFixed(1)}%`}
            />
          ))}
        </div>
        <ul className="mt-3 space-y-1.5">
          {segments.map((s) => (
            <li
              key={s.model}
              className="flex items-center justify-between gap-2 text-[12px]"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className={cn("size-2 shrink-0 rounded-sm", s.className)}
                  aria-hidden
                />
                <span className="truncate font-mono text-[11px] text-foreground">
                  {s.model}
                </span>
              </span>
              <span className="shrink-0 font-mono tabular-nums text-muted-foreground">
                {(s.share * 100).toFixed(1)}%
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
