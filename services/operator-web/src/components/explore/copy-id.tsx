"use client"

import * as React from "react"
import { IconCheck, IconCopy } from "@tabler/icons-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { cn } from "@/lib/utils"

export function CopyId({
  value,
  label,
  className,
}: {
  value: string
  label?: string
  className?: string
}) {
  const [copied, setCopied] = React.useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      toast.success(`Copied ${label ?? "id"}`)
      window.setTimeout(() => setCopied(false), 1200)
    } catch {
      toast.error("Copy failed")
    }
  }

  return (
    <span className={cn("inline-flex items-center gap-1 font-mono", className)}>
      <span className="truncate">{value}</span>
      <Tooltip>
        <TooltipTrigger asChild>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className="size-5 shrink-0"
            onClick={(e) => {
              e.stopPropagation()
              void copy()
            }}
            aria-label={`Copy ${label ?? value}`}
          >
            {copied ? (
              <IconCheck className="size-3" />
            ) : (
              <IconCopy className="size-3" />
            )}
          </Button>
        </TooltipTrigger>
        <TooltipContent>Copy {label ?? "id"}</TooltipContent>
      </Tooltip>
    </span>
  )
}
