"use client"

import * as React from "react"
import { IconLock } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { privilegedActionsEnabled } from "@/lib/sessions/types"
import { cn } from "@/lib/utils"

const GATE_REASON =
  "Disabled until cascade preview ≡ execution, cross-store receipts are wired (F4-019), and replay sandbox negative tests pass. Read-only views ship first."

/** Honest disabled privileged actions — never silent no-ops. */
export function PrivilegedActionButton({
  children,
  className,
  onEnabledClick,
}: {
  children: React.ReactNode
  className?: string
  onEnabledClick?: () => void
}) {
  const enabled = privilegedActionsEnabled()

  if (enabled) {
    return (
      <Button size="sm" className={className} onClick={onEnabledClick}>
        {children}
      </Button>
    )
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="inline-flex">
          <Button size="sm" className={cn(className)} disabled>
            <IconLock className="size-3.5" />
            {children}
          </Button>
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs leading-snug">
        {GATE_REASON}
      </TooltipContent>
    </Tooltip>
  )
}

export function PrivilegedGateBanner({ className }: { className?: string }) {
  if (privilegedActionsEnabled()) return null
  return (
    <p
      className={cn(
        "rounded-md border border-amber-600/30 bg-amber-500/5 px-3 py-2 text-[13px] leading-5 text-amber-900 dark:text-amber-200",
        className,
      )}
    >
      Export / delete / replay stay disabled until honesty gates close — cascade
      preview must equal execution scope, receipts must be wired, and sandbox
      negative tests must pass. Read-only reconstruction ships now.
    </p>
  )
}
