"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
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
import { MEMORY_LIST } from "@/lib/sessions/fixtures"
import type { MemoryLifecycle, MemoryListItem } from "@/lib/sessions/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "success"

const LIFECYCLES: MemoryLifecycle[] = [
  "active",
  "superseded",
  "archived",
  "quarantined",
  "deleted",
]

function lifeTone(
  life: MemoryLifecycle,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (life === "active") return "ok"
  if (life === "quarantined" || life === "deleted") return "error"
  if (life === "superseded") return "warn"
  return "muted"
}

function MemoriesWorkbench() {
  const router = useRouter()
  const [view, setView] = React.useState<ViewState>("loading")
  const [q, setQ] = React.useState("")
  const [life, setLife] = React.useState("all")
  const locked = React.useRef(false)

  React.useEffect(() => {
    const t = window.setTimeout(() => {
      if (!locked.current) setView("success")
    }, 400)
    return () => window.clearTimeout(t)
  }, [])

  const filtered = React.useMemo(() => {
    return MEMORY_LIST.filter((m) => {
      if (life !== "all" && m.lifecycle !== life) return false
      if (!q.trim()) return true
      const needle = q.toLowerCase()
      return (
        m.memory_id.toLowerCase().includes(needle) ||
        m.preview.toLowerCase().includes(needle) ||
        m.category.includes(needle)
      )
    })
  }, [life, q])

  const pager = usePagination(filtered, 15, "accumulate")

  const pills: FilterPill[] = []
  if (life !== "all") {
    pills.push({
      id: "life",
      label: `Lifecycle ${life}`,
      onRemove: () => setLife("all"),
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
        title="Memories"
        description="Provenance, lineage, and retrieval honesty"
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
            description: "Lifecycle, category, or confidence range.",
          })
        }
        trailing={
          <>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="h-8 w-44 text-[13px] md:w-56"
            />
            <Select value={life} onValueChange={setLife}>
              <SelectTrigger
                size="sm"
                className="w-full max-w-[140px] sm:w-[140px]"
              >
                <SelectValue placeholder="Lifecycle" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All lifecycles</SelectItem>
                {LIFECYCLES.map((s) => (
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
          Couldn&apos;t load memories.{" "}
          <span className="font-mono text-muted-foreground">
            GET /v1/memories
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
        <PageEmptyState page="memories" />
      ) : filtered.length === 0 ? (
        <div className="px-1 py-12 text-center text-[13px] text-muted-foreground">
          No memories match these filters.
        </div>
      ) : (
        <MemoryTable
          rows={pager.slice}
          pager={pager}
          onOpen={(id) => router.push(`/dashboard/memories/${id}`)}
        />
      )}
    </div>
  )
}

function MemoryTable({
  rows,
  pager,
  onOpen,
}: {
  rows: MemoryListItem[]
  pager: ReturnType<typeof usePagination<MemoryListItem>>
  onOpen: (id: string) => void
}) {
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Memory</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Category</TableHead>
            <TableHead className={listTable.head}>Confidence</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Sessions
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((m) => (
            <TableRow
              key={m.memory_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => onOpen(m.memory_id)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[360px]")}>
                <Link
                  href={`/dashboard/memories/${m.memory_id}`}
                  className={cn(listTable.primary, "hover:underline")}
                  onClick={(e) => e.stopPropagation()}
                >
                  {m.memory_id}
                </Link>
                <div className={cn(listTable.meta, "mt-0.5 truncate")}>
                  {m.preview}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone={lifeTone(m.lifecycle)} label={m.lifecycle} />
              </TableCell>
              <TableCell className={listTable.cell}>
                <EnvPill>{m.category}</EnvPill>
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {m.confidence.toFixed(2)}
                <span className={listTable.meta}>
                  {" "}
                  · avg {m.avg_composite.toFixed(2)}
                </span>
              </TableCell>
              <TableCell
                className={cn(
                  listTable.cell,
                  listTable.mono,
                  "text-right tabular-nums",
                )}
              >
                {m.retrieved_in_sessions}
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
        label="memories"
        variant="load-more"
      />
    </div>
  )
}

export default function MemoriesPage() {
  return (
    <DashboardShell>
      <MemoriesWorkbench />
    </DashboardShell>
  )
}
