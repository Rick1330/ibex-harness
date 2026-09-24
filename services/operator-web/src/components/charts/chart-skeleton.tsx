"use client"

import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

export function ChartSkeleton({
  className,
  height = 240,
}: {
  className?: string
  height?: number
}) {
  return (
    <div
      className={cn("flex w-full flex-col gap-2", className)}
      style={{ height }}
      aria-hidden
    >
      <div
        className="flex items-end gap-1.5 px-1"
        style={{ height: height - 28 }}
      >
        {Array.from({ length: 18 }).map((_, i) => (
          <Skeleton
            key={i}
            className="flex-1 rounded-sm"
            style={{ height: `${28 + ((i * 37) % 60)}%` }}
          />
        ))}
      </div>
      <Skeleton className="h-3 w-1/3" />
    </div>
  )
}

export function KpiSkeletonRow() {
  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="rounded-lg border border-border/70 px-4 py-3">
          <Skeleton className="h-3 w-16" />
          <Skeleton className="mt-2 h-7 w-24" />
          <Skeleton className="mt-2 h-3 w-14" />
        </div>
      ))}
    </div>
  )
}
