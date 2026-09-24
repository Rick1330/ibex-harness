"use client"

import { IconArchive, IconPlayerPause } from "@tabler/icons-react"

import { Badge } from "@/components/ui/badge"
import type { AgentStatus } from "@/lib/agents/types"
import { cn } from "@/lib/utils"

/**
 * Status badge — color + shape/icon (non-color-redundant).
 * active=filled, paused=outline+icon, suspended=outline+warn, archived=muted+icon
 */
export function AgentStatusBadge({ status }: { status: AgentStatus }) {
  if (status === "active") {
    return (
      <Badge className="border-transparent bg-foreground px-2 py-0 text-[11px] font-medium text-background">
        active
      </Badge>
    )
  }
  if (status === "paused") {
    return (
      <Badge
        variant="outline"
        className="gap-1 px-2 py-0 text-[11px] font-medium text-amber-800 dark:text-amber-200"
      >
        <IconPlayerPause className="size-3" aria-hidden />
        paused
      </Badge>
    )
  }
  if (status === "suspended") {
    return (
      <Badge
        variant="outline"
        className="gap-1 border-destructive/40 px-2 py-0 text-[11px] font-medium text-destructive"
      >
        suspended
      </Badge>
    )
  }
  return (
    <Badge
      variant="outline"
      className={cn(
        "gap-1 px-2 py-0 text-[11px] font-medium text-muted-foreground",
      )}
    >
      <IconArchive className="size-3" aria-hidden />
      archived
    </Badge>
  )
}
