"use client"

import * as React from "react"
import { IconCalendar, IconCheck, IconChevronDown } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"

export type GlobalTimeRange = "15m" | "1h" | "24h" | "7d" | "30d" | "custom"

const PRESETS: { value: Exclude<GlobalTimeRange, "custom">; label: string }[] =
  [
    { value: "15m", label: "last 15m" },
    { value: "1h", label: "last 1h" },
    { value: "24h", label: "last 24h" },
    { value: "7d", label: "last 7d" },
    { value: "30d", label: "last 30d" },
  ]

/**
 * Single global time control for the site header.
 * Visible on all breakpoints (icon-only on narrow screens).
 */
export function TimeRangeControl({ className }: { className?: string }) {
  const [open, setOpen] = React.useState(false)
  const [range, setRange] = React.useState<GlobalTimeRange>("24h")
  const [customFrom, setCustomFrom] = React.useState("2026-02-11T00:00")
  const [customTo, setCustomTo] = React.useState("2026-02-11T14:30")

  const triggerLabel = React.useMemo(() => {
    if (range !== "custom") {
      return PRESETS.find((p) => p.value === range)?.label ?? range
    }
    return formatCustomLabel(customFrom, customTo)
  }, [customFrom, customTo, range])

  return (
    <div className={cn(className)}>
      <DropdownMenu open={open} onOpenChange={setOpen}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="outline"
            size="sm"
            className="h-8 max-w-[200px] gap-1.5 px-2 font-mono text-xs sm:px-2.5"
            aria-label={`Time range: ${triggerLabel}`}
          >
            <IconCalendar className="size-3.5 shrink-0" />
            <span className="hidden truncate sm:inline">{triggerLabel}</span>
            <IconChevronDown className="hidden size-3.5 shrink-0 opacity-60 sm:block" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-72 rounded-xl p-1">
          <DropdownMenuLabel className="px-2 text-xs font-normal text-muted-foreground">
            Time range · applies across the dashboard
          </DropdownMenuLabel>
          {PRESETS.map((p) => (
            <DropdownMenuItem
              key={p.value}
              className="rounded-lg font-mono text-xs"
              onSelect={() => setRange(p.value)}
            >
              <span className="flex-1">{p.label}</span>
              {range === p.value && <IconCheck className="size-3.5" />}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="rounded-lg font-mono text-xs"
            onSelect={(e) => {
              e.preventDefault()
              setRange("custom")
            }}
          >
            <span className="flex-1">custom</span>
            {range === "custom" && <IconCheck className="size-3.5" />}
          </DropdownMenuItem>
          {range === "custom" && (
            <div
              className="flex flex-col gap-2 px-2 pt-1 pb-2"
              onPointerDown={(e) => e.stopPropagation()}
            >
              <label className="flex flex-col gap-1 text-[12px] text-muted-foreground">
                From
                <Input
                  type="datetime-local"
                  value={customFrom}
                  onChange={(e) => setCustomFrom(e.target.value)}
                  className="h-8 font-mono text-xs"
                />
              </label>
              <label className="flex flex-col gap-1 text-[12px] text-muted-foreground">
                To
                <Input
                  type="datetime-local"
                  value={customTo}
                  onChange={(e) => setCustomTo(e.target.value)}
                  className="h-8 font-mono text-xs"
                />
              </label>
              <Button
                type="button"
                size="sm"
                className="mt-1 h-7 text-xs"
                onClick={() => setOpen(false)}
              >
                Apply
              </Button>
            </div>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}

function formatCustomLabel(from: string, to: string) {
  const a = shortDate(from)
  const b = shortDate(to)
  if (!a || !b) return "custom"
  return `${a} – ${b}`
}

function shortDate(value: string) {
  try {
    const d = new Date(value)
    if (Number.isNaN(d.getTime())) return null
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return null
  }
}
