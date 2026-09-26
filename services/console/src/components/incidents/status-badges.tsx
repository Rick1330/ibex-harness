"use client"

import { Badge } from "@/components/ui/badge"
import type { IncidentSeverity, IncidentStatus } from "@/lib/incidents/types"
import { cn } from "@/lib/utils"

const sevTone: Record<IncidentSeverity, string> = {
  sev1: "border-destructive/50 text-destructive",
  sev2: "border-orange-600/50 text-orange-800 dark:text-orange-300",
  sev3: "border-amber-600/40 text-amber-900 dark:text-amber-200",
  sev4: "border-muted-foreground/40 text-muted-foreground",
}

const statusTone: Record<IncidentStatus, string> = {
  open: "border-destructive/40 text-destructive",
  acknowledged: "border-amber-600/40 text-amber-900 dark:text-amber-200",
  mitigating: "border-sky-600/40 text-sky-800 dark:text-sky-300",
  resolved: "border-emerald-600/40 text-emerald-800 dark:text-emerald-300",
  closed: "border-muted-foreground/30 text-muted-foreground",
}

export function SeverityBadge({ severity }: { severity: IncidentSeverity }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px] uppercase", sevTone[severity])}
    >
      {severity}
    </Badge>
  )
}

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  return (
    <Badge
      variant="outline"
      className={cn("font-mono text-[13px]", statusTone[status])}
    >
      ●{status}
    </Badge>
  )
}
