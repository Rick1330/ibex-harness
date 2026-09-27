"use client"

import { ExploreQueryBar } from "@/components/explore/query-bar"
import { TracePreviewPanel } from "@/components/explore/trace-preview-panel"
import { TracesTable } from "@/components/explore/traces-table"
import { ListPageHeader } from "@/components/list/filter-bar"
import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  FailuresTable,
  SessionsTable,
} from "@/app/dashboard/explore/preview-tables"
import type { ExploreTab, QueryChip, TraceListItem } from "@/lib/explore/types"
import { panelClass } from "@/components/sessions/dashboard-shell"

export type PreviewViewState = "loading" | "empty" | "error" | "success"

type PreviewContentProps = {
  readonly view: PreviewViewState
  readonly chips: QueryChip[]
  readonly tab: ExploreTab
  readonly traces: TraceListItem[]
  readonly counts: {
    readonly traces: number
    readonly sessions: number
    readonly failures: number
  }
  readonly hoveredId: string | null
  readonly hovered: TraceListItem | null
  readonly onPreview: (view: PreviewViewState) => void
  readonly onRetry: () => void
  readonly onChipsChange: (chips: QueryChip[]) => void
  readonly onSaveView: () => void
  readonly onTabChange: (tab: ExploreTab) => void
  readonly onHover: (id: string | null) => void
  readonly onSelect: (id: string) => void
}

export function PreviewContent({
  view,
  chips,
  tab,
  traces,
  counts,
  hoveredId,
  hovered,
  onPreview,
  onRetry,
  onChipsChange,
  onSaveView,
  onTabChange,
  onHover,
  onSelect,
}: PreviewContentProps) {
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
        <>
          <ListPageHeader
            title="Explore"
            description="Global traces, sessions, and failures"
            actions={
              <div className="flex items-center gap-1">
                {(
                  ["loading", "empty", "error", "success"] as PreviewViewState[]
                ).map((state) => (
                  <Button
                    key={state}
                    size="sm"
                    variant={view === state ? "default" : "ghost"}
                    className="h-7 px-2 text-[12px] capitalize"
                    onClick={() => {
                      onPreview(state)
                    }}
                  >
                    {state}
                  </Button>
                ))}
              </div>
            }
          />
          <div className="min-w-0">
            <ExploreQueryBar
              chips={chips}
              onChipsChange={onChipsChange}
              onSaveView={onSaveView}
            />
          </div>
          <Tabs
            value={tab}
            onValueChange={(value) => {
              onTabChange(value as ExploreTab)
            }}
          >
            <TabsList variant="line">
              <TabsTrigger value="traces" className="text-[13px]">
                Traces{" "}
                <span className="font-mono text-[13px] text-muted-foreground">
                  {counts.traces}
                </span>
              </TabsTrigger>
              <TabsTrigger value="sessions" className="text-[13px]">
                Sessions{" "}
                <span className="font-mono text-[13px] text-muted-foreground">
                  {counts.sessions}
                </span>
              </TabsTrigger>
              <TabsTrigger value="failures" className="text-[13px]">
                Failures{" "}
                <span className="font-mono text-[13px] text-muted-foreground">
                  {counts.failures}
                </span>
              </TabsTrigger>
            </TabsList>
            <TabsContent value="traces" className="mt-3">
              {view === "empty" && <PageEmptyState page="explore" />}
              {view !== "empty" && traces.length === 0 && (
                <div className="px-1 py-10 text-center text-[13px] text-muted-foreground">
                  No traces match this query. Cross-tenant{" "}
                  <span className="font-mono">trace_id</span> lookups return
                  empty / 404 — never &quot;found but forbidden&quot;.
                </div>
              )}
              {view !== "empty" && traces.length > 0 && (
                <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,320px)]">
                  <TracesTable
                    rows={traces}
                    hoveredId={hoveredId}
                    onHover={onHover}
                    onSelect={onSelect}
                  />
                  <TracePreviewPanel trace={hovered} />
                </div>
              )}
            </TabsContent>
            <TabsContent value="sessions" className="mt-3">
              <SessionsTable />
            </TabsContent>
            <TabsContent value="failures" className="mt-3">
              <FailuresTable />
            </TabsContent>
          </Tabs>
        </>
      )}
    </div>
  )
}
