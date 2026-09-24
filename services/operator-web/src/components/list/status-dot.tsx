"use client"

import type { ReactNode } from "react"

import { cn } from "@/lib/utils"

const toneDot: Record<"ok" | "error" | "warn" | "muted" | "info", string> = {
  ok: "bg-emerald-500",
  error: "bg-red-500",
  warn: "bg-amber-500",
  muted: "bg-muted-foreground/50",
  info: "bg-sky-500",
}

/** Vercel-style status: colored dot + label (+ optional duration). */
export function StatusDot({
  tone,
  label,
  detail,
  className,
}: {
  tone: keyof typeof toneDot
  label: string
  detail?: string
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap text-[12px]",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("size-1.5 shrink-0 rounded-full", toneDot[tone])}
      />
      <span className="text-foreground">{label}</span>
      {detail ? <span className="text-muted-foreground">{detail}</span> : null}
    </span>
  )
}

export function EnvPill({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-border bg-background px-2 py-0.5 text-[11px] text-muted-foreground whitespace-nowrap",
        className,
      )}
    >
      {children}
    </span>
  )
}
