"use client"

import type { ReactNode } from "react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

/**
 * Mandated loading/error/empty pattern — title, description, optional action.
 * Quiet editorial empty; no emoji, no confetti.
 */
export function EmptyState({
  title,
  description,
  action,
  className,
}: {
  title: string
  description?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-col items-center px-4 py-14 text-center",
        className,
      )}
    >
      <div className="text-[14px] font-medium tracking-tight text-foreground">
        {title}
      </div>
      {description ? (
        <p className="mt-1.5 max-w-md text-[12px] leading-relaxed text-muted-foreground">
          {description}
        </p>
      ) : null}
      {action ? (
        <div className="mt-4 flex flex-wrap justify-center gap-2">{action}</div>
      ) : null}
    </div>
  )
}

export function EmptyStateButton({
  children,
  onClick,
  href,
  variant = "default",
}: {
  children: ReactNode
  onClick?: () => void
  href?: string
  variant?: "default" | "outline" | "ghost"
}) {
  if (href) {
    return (
      <Button asChild size="sm" variant={variant} className="h-8">
        <a href={href}>{children}</a>
      </Button>
    )
  }
  return (
    <Button size="sm" variant={variant} className="h-8" onClick={onClick}>
      {children}
    </Button>
  )
}
