"use client"

import { Badge } from "@/components/ui/badge"
import type { EvidenceBadges, TraceStatus } from "@/lib/explore/types"
import { cn } from "@/lib/utils"

const statusClass: Record<TraceStatus, string> = {
  success: "border-transparent bg-foreground text-background",
  error: "border-transparent bg-destructive text-white",
  partial: "border-border bg-muted text-foreground",
}

export function StatusBadge({ status }: { status: TraceStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px]", statusClass[status])}
    >
      {status}
    </Badge>
  )
}

export function EvidenceBadgeRow({
  evidence,
  className,
  compact = false,
}: {
  evidence: EvidenceBadges
  className?: string
  /** Single-line row for table cells — never wraps vertically. */
  compact?: boolean
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-1",
        compact ? "flex-nowrap whitespace-nowrap" : "flex-wrap",
        className,
      )}
    >
      <DotBadge
        label={evidence.completeness}
        tone={evidence.completeness === "complete" ? "ok" : "warn"}
        compact={compact}
      />
      <DotBadge
        label={
          compact
            ? evidence.sampled
              ? "sampled"
              : "full"
            : `sampled:${evidence.sampled}`
        }
        tone={evidence.sampled ? "warn" : "muted"}
        compact={compact}
      />
      <DotBadge
        label={evidence.freshness}
        tone={evidence.freshness === "fresh" ? "ok" : "warn"}
        compact={compact}
      />
      <DotBadge
        label={
          evidence.retention_days == null
            ? compact
              ? "ret:—"
              : "retention:—"
            : compact
              ? `${evidence.retention_days}d`
              : `retention:${evidence.retention_days}d`
        }
        tone="muted"
        compact={compact}
      />
    </div>
  )
}

function DotBadge({
  label,
  tone,
  compact,
}: {
  label: string
  tone: "ok" | "warn" | "muted"
  compact?: boolean
}) {
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full border font-mono whitespace-nowrap",
        compact ? "px-1.5 py-0 text-[13px]" : "px-2 py-0.5 text-[13px]",
        tone === "ok" && "border-foreground/20 text-foreground",
        tone === "warn" &&
          "border-amber-600/40 text-amber-800 dark:text-amber-300",
        tone === "muted" && "border-border text-muted-foreground",
      )}
    >
      <span
        aria-hidden
        className={cn(
          "rounded-full",
          compact ? "size-1" : "size-1.5",
          tone === "ok" && "bg-foreground",
          tone === "warn" && "bg-amber-600",
          tone === "muted" && "bg-muted-foreground",
        )}
      />
      {label}
    </span>
  )
}

export function DispositionBadge({
  disposition,
}: {
  disposition: "included" | "budget_excluded" | "filtered" | "failed"
}) {
  const map = {
    included: {
      label: "Included",
      className:
        "border-transparent bg-[oklch(0.52_0.1_185)] text-white dark:bg-[oklch(0.7_0.1_185)] dark:text-[oklch(0.15_0.02_185)]",
    },
    budget_excluded: {
      label: "Budget",
      className:
        "border-transparent bg-[oklch(0.58_0.13_55)] text-[oklch(0.22_0.05_55)] dark:bg-[oklch(0.75_0.12_55)]",
    },
    filtered: {
      label: "Filtered",
      className:
        "border-transparent bg-[oklch(0.48_0.06_250)] text-white dark:bg-[oklch(0.68_0.07_250)]",
    },
    failed: {
      label: "Failed",
      className: "border-transparent bg-destructive text-white",
    },
  } as const
  const m = map[disposition]
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px]", m.className)}
    >
      {m.label}
    </Badge>
  )
}
