"use client"

import type { ComponentProps } from "react"

import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { panelClass } from "@/components/sessions/dashboard-shell"

import {
  PreviewReadyContent,
} from "@/app/dashboard/explore/preview-ready"

export type { PreviewViewState } from "@/app/dashboard/explore/preview-ready"

export function PreviewContent(
  props: ComponentProps<typeof PreviewReadyContent> & {
    readonly onRetry: () => void
  },
) {
  const { view, onRetry } = props
  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-3 px-4 py-4 md:py-5 lg:px-6">
      {view === "loading" && (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-12 w-full rounded-lg" />
          <Skeleton className="h-9 w-64 rounded-lg" />
          <Skeleton className="h-[280px] w-full rounded-lg" />
        </div>
      )}
      {view === "error" && (
        <Card className={`${panelClass} gap-0 py-0`}>
          <CardContent className="px-4 py-8 text-center">
            <div className="text-[13px] font-medium">
              Couldn&apos;t load Explore
            </div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              <span className="font-mono">GET /v1/traces</span> failed.
            </p>
            <Button size="sm" className="mt-3" onClick={onRetry}>
              Retry
            </Button>
          </CardContent>
        </Card>
      )}
      {view !== "loading" && view !== "error" && (
        <PreviewReadyContent {...props} />
      )}
    </div>
  )
}
