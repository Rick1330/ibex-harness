"use client"

import type { ReactNode } from "react"
import { IconFilter, IconX } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export type FilterPill = {
  id: string
  label: string
  onRemove?: () => void
}

/** Vercel-style filter strip: Add Filter + removable pills. */
export function FilterBar({
  pills,
  onAddFilter,
  trailing,
  className,
}: {
  pills: FilterPill[]
  onAddFilter?: () => void
  trailing?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        "flex flex-wrap items-center gap-2 border-b border-border/60 pb-3",
        className,
      )}
    >
      {onAddFilter ? (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 gap-1.5 rounded-md border-border bg-transparent text-[12px] text-muted-foreground hover:text-foreground"
          onClick={onAddFilter}
        >
          <IconFilter className="size-3.5" />
          Add Filter
        </Button>
      ) : null}
      {pills.map((p) => (
        <span
          key={p.id}
          className="inline-flex max-w-full items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-1 text-[12px] text-foreground"
        >
          <span className="truncate">{p.label}</span>
          {p.onRemove ? (
            <button
              type="button"
              aria-label={`Remove ${p.label}`}
              className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              onClick={p.onRemove}
            >
              <IconX className="size-3.5" />
            </button>
          ) : null}
        </span>
      ))}
      {trailing ? (
        <div className="ml-auto flex min-w-0 flex-wrap items-center gap-2">
          {trailing}
        </div>
      ) : null}
    </div>
  )
}

/**
 * Page chrome under the site header.
 * Title is omitted visually by default — the header breadcrumb already shows
 * the page name. Pass showTitle for detail pages with a resource-specific name.
 */
export function ListPageHeader({
  title,
  description,
  actions,
  showTitle = false,
}: {
  title?: string
  description?: string
  actions?: ReactNode
  /** When true, render a visible h1 (detail / resource pages). */
  showTitle?: boolean
}) {
  if (!showTitle && !description && !actions) return null

  return (
    <div className="mb-1 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        {showTitle && title ? (
          <h1 className="text-[18px] font-semibold tracking-tight text-foreground">
            {title}
          </h1>
        ) : title ? (
          <h1 className="sr-only">{title}</h1>
        ) : null}
        {description ? (
          <p
            className={cn(
              "text-[12px] text-muted-foreground",
              showTitle && title && "mt-0.5",
            )}
          >
            {description}
          </p>
        ) : null}
      </div>
      {actions ? (
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {actions}
        </div>
      ) : null}
    </div>
  )
}
