"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"

import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { listTable } from "@/components/explore/table-styles"
import {
  FilterBar,
  ListPageHeader,
  type FilterPill,
} from "@/components/list/filter-bar"
import { EnvPill, StatusDot } from "@/components/list/status-dot"
import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import { DashboardShell, pagePad } from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { SESSION_LIST } from "@/lib/sessions/fixtures"
import type { SessionListItem, SessionStatus } from "@/lib/sessions/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "success"

const STATUSES: SessionStatus[] = [
  "initializing",
  "active",
  "suspended",
  "resuming",
  "completed",
  "failed",
  "abandoned",
]

function sessionTone(
  status: SessionStatus,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (status === "completed" || status === "active") return "ok"
  if (status === "failed") return "error"
  if (status === "abandoned" || status === "suspended") return "warn"
  return "muted"
}

function SessionsWorkbench() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [view, setView] = React.useState<ViewState>("loading")
  const [q, setQ] = React.useState(searchParams.get("q") ?? "")
  const [status, setStatus] = React.useState<string>(
    searchParams.get("status") ?? "all",
  )
  const locked = React.useRef(false)

  React.useEffect(() => {
    const t = window.setTimeout(() => {
      if (!locked.current) setView("success")
    }, 400)
    return () => window.clearTimeout(t)
  }, [])

  const filtered = React.useMemo(() => {
    return SESSION_LIST.filter((s) => {
      if (status !== "all" && s.status !== status) return false
      if (!q.trim()) return true
      const needle = q.toLowerCase()
      return (
        s.session_id.toLowerCase().includes(needle) ||
        s.agent.toLowerCase().includes(needle) ||
        s.tags.some((t) => t.includes(needle))
      )
    })
  }, [q, status])

  const pager = usePagination(filtered, 15, "accumulate")

  const pills: FilterPill[] = []
  if (status !== "all") {
    pills.push({
      id: "status",
      label: `Status ${status}`,
      onRemove: () => setStatus("all"),
    })
  }
  if (q.trim()) {
    pills.push({
      id: "q",
      label: `Search ${q.trim()}`,
      onRemove: () => setQ(""),
    })
  }

  return (
    <div className={pagePad}>
      <ListPageHeader
        title="Sessions"
        description="Turn-by-turn reconstruction · governed export/delete/replay"
        actions={
          <div className="flex gap-1">
            {(["loading", "empty", "error", "success"] as ViewState[]).map(
              (v) => (
                <Button
                  key={v}
                  size="sm"
                  variant={view === v ? "default" : "ghost"}
                  className="h-7 px-2 text-[12px] capitalize"
                  onClick={() => {
                    locked.current = true
                    setView(v)
                  }}
                >
                  {v}
                </Button>
              ),
            )}
          </div>
        }
      />

      <FilterBar
        pills={pills}
        onAddFilter={() =>
          toast.message("Add Filter", {
            description: "Pick status, agent, or tag — pills appear here.",
          })
        }
        trailing={
          <>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="h-8 w-44 text-[13px] md:w-56"
              aria-label="Search sessions"
            />
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger
                size="sm"
                className="w-[130px]"
                aria-label="Status"
              >
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </>
        }
      />

      {view === "loading" ? (
        <div className="space-y-0 pt-2">
          {Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-none border-b" />
          ))}
        </div>
      ) : view === "error" ? (
        <div className="px-1 py-12 text-center text-[13px]">
          Couldn&apos;t load sessions.{" "}
          <span className="font-mono text-muted-foreground">
            GET /v1/sessions
          </span>{" "}
          failed.
          <div className="mt-3">
            <Button
              size="sm"
              onClick={() => {
                locked.current = true
                setView("loading")
                window.setTimeout(() => setView("success"), 500)
              }}
            >
              Retry
            </Button>
          </div>
        </div>
      ) : view === "empty" ? (
        <PageEmptyState page="sessions" />
      ) : filtered.length === 0 ? (
        <div className="px-1 py-12 text-center text-[13px] text-muted-foreground">
          No sessions match these filters.
        </div>
      ) : (
        <SessionsTable
          rows={pager.slice}
          pager={pager}
          onOpen={(id) => router.push(`/dashboard/sessions/${id}`)}
        />
      )}
    </div>
  )
}

function SessionsTable({
  rows,
  pager,
  onOpen,
}: {
  rows: SessionListItem[]
  pager: ReturnType<typeof usePagination<SessionListItem>>
  onOpen: (id: string) => void
}) {
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Session</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Directive</TableHead>
            <TableHead className={listTable.head}>Tags</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Heartbeat
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((s) => (
            <TableRow
              key={s.session_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => onOpen(s.session_id)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[260px]")}>
                <Link
                  href={`/dashboard/sessions/${s.session_id}`}
                  className={cn(listTable.primary, "hover:underline")}
                  onClick={(e) => e.stopPropagation()}
                >
                  {s.session_id}
                </Link>
                <div className={cn(listTable.meta, "mt-0.5")}>
                  {s.turn_count} turns · {s.duration_ms}ms
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone={sessionTone(s.status)} label={s.status} />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {s.agent}
              </TableCell>
              <TableCell className={listTable.cell}>
                <EnvPill>v{s.directive_version}</EnvPill>
              </TableCell>
              <TableCell className={listTable.cell}>
                <div className="flex flex-wrap gap-1">
                  {s.tags.slice(0, 3).map((t) => (
                    <EnvPill key={t}>{t}</EnvPill>
                  ))}
                </div>
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {s.last_heartbeat_ago}
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

export default function SessionsPage() {
  return (
    <DashboardShell>
      <React.Suspense
        fallback={
          <div className={pagePad}>
            <Skeleton className="h-12 w-full rounded-lg" />
          </div>
        }
      >
        <SessionsWorkbench />
      </React.Suspense>
    </DashboardShell>
  )
}
