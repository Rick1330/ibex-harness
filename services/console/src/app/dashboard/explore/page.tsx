"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"

import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { ExploreQueryBar } from "@/components/explore/query-bar"
import { TracePreviewPanel } from "@/components/explore/trace-preview-panel"
import { TracesTable } from "@/components/explore/traces-table"
import { listTable } from "@/components/explore/table-styles"
import { ListPageHeader } from "@/components/list/filter-bar"
import { StatusDot } from "@/components/list/status-dot"
import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { FAILURE_LIST, SESSION_LIST, TRACE_LIST } from "@/lib/explore/fixtures"
import type { ExploreTab, QueryChip, TraceListItem } from "@/lib/explore/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "success"

function filterTraces(rows: TraceListItem[], chips: QueryChip[]) {
  if (!chips.length) return rows
  return rows.filter((row) =>
    chips.every((chip) => {
      switch (chip.field) {
        case "agent":
          return row.agent.toLowerCase().includes(chip.value.toLowerCase())
        case "session":
          return row.session_id.toLowerCase().includes(chip.value.toLowerCase())
        case "model":
          return row.model.toLowerCase().includes(chip.value.toLowerCase())
        case "provider":
          return row.provider.toLowerCase().includes(chip.value.toLowerCase())
        case "status":
          return row.status === chip.value
        case "text":
          return (
            row.trace_id.includes(chip.value) ||
            row.agent.toLowerCase().includes(chip.value.toLowerCase())
          )
        default:
          return true
      }
    }),
  )
}

const QUERY_FIELDS = [
  "agent",
  "session",
  "model",
  "provider",
  "status",
  "error",
  "directive_version",
  "tool",
] as const

function parseChips(q: string | null): QueryChip[] {
  if (!q) return []
  return q
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => {
      const idx = part.indexOf(":")
      if (idx > 0) {
        const field = part.slice(0, idx)
        const value = part.slice(idx + 1)
        return {
          id: `${field}-${value}`,
          field: (QUERY_FIELDS as readonly string[]).includes(field)
            ? (field as QueryChip["field"])
            : "text",
          value,
        }
      }
      return { id: `text-${part}`, field: "text" as const, value: part }
    })
}

function parseTab(v: string | null): ExploreTab {
  if (v && ["traces", "sessions", "failures"].includes(v)) {
    return v as ExploreTab
  }
  return "traces"
}

function ExploreWorkbench() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const chips = React.useMemo(
    () => parseChips(searchParams.get("q")),
    [searchParams],
  )
  const tab = parseTab(searchParams.get("tab"))

  const [view, setView] = React.useState<ViewState>("loading")
  const [hoveredId, setHoveredId] = React.useState<string | null>(null)
  const locked = React.useRef(false)

  React.useEffect(() => {
    const t = window.setTimeout(() => {
      if (!locked.current) setView("success")
    }, 700)
    return () => window.clearTimeout(t)
  }, [])

  const syncUrl = React.useCallback(
    (next: { chips?: QueryChip[]; tab?: ExploreTab }) => {
      const params = new URLSearchParams()
      const c = next.chips ?? chips
      const tb = next.tab ?? tab
      if (c.length) {
        params.set(
          "q",
          c
            .map((chip) =>
              chip.field === "text"
                ? chip.value
                : `${chip.field}:${chip.value}`,
            )
            .join(" "),
        )
      }
      params.set("tab", tb)
      router.replace(`/dashboard/explore?${params.toString()}`, {
        scroll: false,
      })
    },
    [chips, router, tab],
  )

  const traces = filterTraces(TRACE_LIST, chips)
  const hovered = traces.find((t) => t.trace_id === hoveredId) ?? null

  const counts = {
    traces: traces.length,
    sessions: SESSION_LIST.length,
    failures: FAILURE_LIST.length,
  }

  const preview = (v: ViewState) => {
    locked.current = true
    setView(v)
  }

  const saveView = () => {
    syncUrl({})
    void navigator.clipboard.writeText(window.location.href)
    toast.success("Saved view URL copied", {
      description:
        "Pin it under ★ Pinned — views are URLs, not server objects.",
    })
  }

  return (
    <div className="mx-auto flex w-full max-w-[1440px] flex-col gap-3 px-4 py-4 md:py-5 lg:px-6">
      {view === "loading" ? (
        <div className="flex flex-col gap-3">
          <Skeleton className="h-12 w-full rounded-lg" />
          <Skeleton className="h-9 w-64 rounded-lg" />
          <Skeleton className="h-[280px] w-full rounded-lg" />
        </div>
      ) : view === "error" ? (
        <Card className={`${panelClass} gap-0 py-0`}>
          <CardContent className="px-4 py-8 text-center">
            <div className="text-[13px] font-medium">
              Couldn&apos;t load Explore
            </div>
            <p className="mt-1 text-[13px] text-muted-foreground">
              <span className="font-mono">GET /v1/traces</span> failed.
            </p>
            <Button
              size="sm"
              className="mt-3"
              onClick={() => {
                locked.current = true
                setView("loading")
                window.setTimeout(() => setView("success"), 800)
              }}
            >
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : (
        <>
          <ListPageHeader
            title="Explore"
            description="Global traces, sessions, and failures"
            actions={
              <div className="flex items-center gap-1">
                {(["loading", "empty", "error", "success"] as ViewState[]).map(
                  (v) => (
                    <Button
                      key={v}
                      size="sm"
                      variant={view === v ? "default" : "ghost"}
                      className="h-7 px-2 text-[12px] capitalize"
                      onClick={() => preview(v)}
                    >
                      {v}
                    </Button>
                  ),
                )}
              </div>
            }
          />

          <div className="min-w-0">
            <ExploreQueryBar
              chips={chips}
              onChipsChange={(next) => syncUrl({ chips: next })}
              onSaveView={saveView}
            />
          </div>

          <Tabs
            value={tab}
            onValueChange={(v) => syncUrl({ tab: v as ExploreTab })}
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
              {view === "empty" ? (
                <PageEmptyState page="explore" />
              ) : traces.length === 0 ? (
                <div className="px-1 py-10 text-center text-[13px] text-muted-foreground">
                  No traces match this query. Cross-tenant{" "}
                  <span className="font-mono">trace_id</span> lookups return
                  empty / 404 — never &quot;found but forbidden&quot;.
                </div>
              ) : (
                <div className="grid items-start gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(260px,320px)]">
                  <TracesTable
                    rows={traces}
                    hoveredId={hoveredId}
                    onHover={setHoveredId}
                    onSelect={(id) => router.push(`/dashboard/explore/t/${id}`)}
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

function SessionsTable() {
  const pager = usePagination(SESSION_LIST, 12, "accumulate")

  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Session</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Model</TableHead>
            <TableHead className={listTable.head}>Traces</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Last active
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pager.slice.map((s) => (
            <TableRow key={s.session_id} className={listTable.row}>
              <TableCell className={cn(listTable.cell, listTable.primary)}>
                {s.session_id}
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot
                  tone={
                    s.status === "success"
                      ? "ok"
                      : s.status === "error"
                        ? "error"
                        : "warn"
                  }
                  label={s.status}
                />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {s.agent}
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {s.model}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {s.trace_count}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {s.last_active}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <PaginationBar
        page={pager.page}
        pageCount={pager.pageCount}
        total={pager.total}
        from={pager.from}
        to={pager.to}
        onPageChange={pager.setPage}
        label="sessions"
        variant="load-more"
      />
    </div>
  )
}

function FailuresTable() {
  const router = useRouter()
  const pager = usePagination(FAILURE_LIST, 12, "accumulate")

  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Failure</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Model</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Started
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pager.slice.map((f) => (
            <TableRow
              key={f.trace_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => router.push(`/dashboard/explore/t/${f.trace_id}`)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[280px]")}>
                <div className={listTable.primary}>{f.trace_id}</div>
                <div className={cn(listTable.meta, "mt-0.5 text-destructive")}>
                  {f.error}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone="error" label="error" />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {f.agent}
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {f.model}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {f.started_at}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <PaginationBar
        page={pager.page}
        pageCount={pager.pageCount}
        total={pager.total}
        from={pager.from}
        to={pager.to}
        onPageChange={pager.setPage}
        label="failures"
        variant="load-more"
      />
    </div>
  )
}

export default function ExplorePage() {
  return (
    <DashboardShell>
      <React.Suspense
        fallback={
          <div className={pagePad}>
            <Skeleton className="h-24 w-full rounded-lg" />
          </div>
        }
      >
        <ExploreWorkbench />
      </React.Suspense>
    </DashboardShell>
  )
}
