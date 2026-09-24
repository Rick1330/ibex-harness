"use client"

import * as React from "react"
import { IconChevronLeft, IconChevronRight } from "@tabler/icons-react"

import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function usePagination<T>(
  items: T[],
  pageSize = 10,
  mode: "page" | "accumulate" = "page",
) {
  const [page, setPage] = React.useState(1)
  const total = items.length
  const pageCount = Math.max(1, Math.ceil(total / pageSize) || 1)
  // Clamp without an effect — derived safe page.
  const safePage = Math.min(Math.max(1, page), pageCount)
  const start = (safePage - 1) * pageSize
  const slice =
    mode === "accumulate"
      ? items.slice(0, safePage * pageSize)
      : items.slice(start, start + pageSize)

  const goTo = React.useCallback(
    (next: number) => {
      setPage(Math.min(Math.max(1, next), pageCount))
    },
    [pageCount],
  )

  const setPageSafe = React.useCallback(
    (next: number) => {
      goTo(next)
    },
    [goTo],
  )

  return {
    page: safePage,
    setPage: setPageSafe,
    pageSize,
    pageCount,
    total,
    slice,
    from: total === 0 ? 0 : mode === "accumulate" ? 1 : start + 1,
    to: Math.min(
      mode === "accumulate" ? safePage * pageSize : start + pageSize,
      total,
    ),
  }
}

export function PaginationBar({
  page,
  pageCount,
  total,
  from,
  to,
  onPageChange,
  className,
  label = "rows",
  variant = "pager",
}: {
  page: number
  pageCount: number
  total: number
  from: number
  to: number
  onPageChange: (page: number) => void
  className?: string
  label?: string
  /** `load-more` matches Vercel Deployments footer. */
  variant?: "pager" | "load-more"
}) {
  if (total === 0) return null

  if (variant === "load-more") {
    const hasMore = page < pageCount
    return (
      <div className={cn("pt-2", className)}>
        {hasMore ? (
          <Button
            type="button"
            variant="secondary"
            className="h-10 w-full rounded-md text-[12px] font-medium text-muted-foreground hover:text-foreground"
            onClick={() => onPageChange(page + 1)}
          >
            Load More
          </Button>
        ) : (
          <p className="py-2 text-center text-[12px] text-muted-foreground tabular-nums">
            Showing all {total} {label}
          </p>
        )}
      </div>
    )
  }

  return (
    <div
      className={cn(
        "flex flex-wrap items-center justify-between gap-2 border-t border-border/60 px-1 py-3",
        className,
      )}
    >
      <span className="text-[12px] text-muted-foreground tabular-nums">
        {from}–{to} of {total} {label}
      </span>
      <div className="flex items-center gap-1">
        <Button
          type="button"
          size="icon-xs"
          variant="outline"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          aria-label="Previous page"
        >
          <IconChevronLeft className="size-3.5" />
        </Button>
        <span className="min-w-14 text-center text-[12px] tabular-nums text-muted-foreground">
          {page} / {pageCount}
        </span>
        <Button
          type="button"
          size="icon-xs"
          variant="outline"
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
          aria-label="Next page"
        >
          <IconChevronRight className="size-3.5" />
        </Button>
      </div>
    </div>
  )
}
