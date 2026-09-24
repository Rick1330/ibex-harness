"use client"

import { Badge } from "@/components/ui/badge"
import type {
  JobStatus,
  MemoryLifecycle,
  SessionStatus,
  TurnKind,
} from "@/lib/sessions/types"
import { cn } from "@/lib/utils"

export function SessionStatusBadge({ status }: { status: SessionStatus }) {
  const tone =
    status === "completed"
      ? "bg-foreground text-background"
      : status === "failed" || status === "abandoned"
        ? "bg-destructive text-white"
        : status === "active" || status === "resuming"
          ? "border-foreground/30"
          : "bg-muted text-foreground"

  return (
    <Badge variant="outline" className={cn("font-mono text-[13px]", tone)}>
      {status}
    </Badge>
  )
}

export function LifecycleBadge({ status }: { status: MemoryLifecycle }) {
  const tone =
    status === "active"
      ? "bg-foreground text-background"
      : status === "quarantined" || status === "deleted"
        ? "border-amber-600/40 text-amber-800 dark:text-amber-300"
        : "bg-muted text-foreground"

  return (
    <Badge variant="outline" className={cn("font-mono text-[13px]", tone)}>
      {status}
    </Badge>
  )
}

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const tone =
    status === "completed"
      ? "bg-foreground text-background"
      : status === "failed"
        ? "bg-destructive text-white"
        : status === "parked"
          ? "border-amber-600/40 text-amber-800 dark:text-amber-300"
          : "bg-muted text-foreground"

  return (
    <Badge variant="outline" className={cn("font-mono text-[13px]", tone)}>
      {status}
    </Badge>
  )
}

export function TurnKindBadge({ kind }: { kind: TurnKind }) {
  const special =
    kind === "missing" || kind === "redacted" || kind === "sampled"
  return (
    <Badge
      variant="outline"
      className={cn(
        "font-mono text-[13px]",
        special && "border-amber-600/40 text-amber-800 dark:text-amber-300",
      )}
    >
      {kind}
    </Badge>
  )
}
