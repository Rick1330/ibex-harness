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
import { StatusDot } from "@/components/list/status-dot"
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
import { INCIDENT_LIST } from "@/lib/incidents/fixtures"
import type {
  IncidentListItem,
  IncidentSeverity,
  IncidentStatus,
} from "@/lib/incidents/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "success"

const STATUSES: IncidentStatus[] = [
  "open",
  "acknowledged",
  "mitigating",
  "resolved",
  "closed",
]

const SEVERITIES: IncidentSeverity[] = ["sev1", "sev2", "sev3", "sev4"]

function sevTone(
  s: IncidentSeverity,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (s === "sev1") return "error"
  if (s === "sev2") return "warn"
  if (s === "sev3") return "info"
  return "muted"
}

function statusTone(
  s: IncidentStatus,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (s === "resolved" || s === "closed") return "ok"
  if (s === "open") return "error"
  if (s === "mitigating") return "info"
  return "warn"
}

function IncidentsWorkbench() {
  const router = useRouter()
  const [view, setView] = React.useState<ViewState>("loading")
  const [q, setQ] = React.useState("")
  const [status, setStatus] = React.useState("all")
  const [severity, setSeverity] = React.useState("all")
  const [owner, setOwner] = React.useState("all")

  React.useEffect(() => {
    const t = window.setTimeout(() => setView("success"), 400)
    return () => window.clearTimeout(t)
  }, [])

  const filtered = React.useMemo(() => {
    return INCIDENT_LIST.filter((i) => {
      if (status !== "all" && i.status !== status) return false
      if (severity !== "all" && i.severity !== severity) return false
      if (owner === "unassigned" && i.owner !== null) return false
      if (owner !== "all" && owner !== "unassigned" && i.owner !== owner)
        return false
      if (!q.trim()) return true
      const needle = q.toLowerCase()
      return (
        i.incident_id.toLowerCase().includes(needle) ||
        i.title.toLowerCase().includes(needle) ||
        i.dedupe_key.toLowerCase().includes(needle) ||
        (i.owner?.toLowerCase().includes(needle) ?? false)
      )
    })
  }, [q, status, severity, owner])

  const pager = usePagination(filtered, 15, "accumulate")

  const pills: FilterPill[] = []
  if (status !== "all") {
    pills.push({
      id: "status",
      label: `Status ${status}`,
      onRemove: () => setStatus("all"),
    })
  }
  if (severity !== "all") {
    pills.push({
      id: "sev",
      label: `Severity ${severity.toUpperCase()}`,
      onRemove: () => setSeverity("all"),
    })
  }
  if (owner !== "all") {
    pills.push({
      id: "owner",
      label: owner === "unassigned" ? "Unassigned" : `Owner @${owner}`,
      onRemove: () => setOwner("all"),
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
        title="Incidents"
        description="Triage, ownership, evidence bundles — not raw failed_tasks"
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() =>
                toast.message("New incident", {
                  description: "dedupe_key prevents duplicate signatures.",
                })
              }
            >
              + New Incident
            </Button>
            <div className="flex gap-1">
              {(["loading", "empty", "error", "success"] as ViewState[]).map(
                (v) => (
                  <Button
                    key={v}
                    size="sm"
                    variant={view === v ? "default" : "ghost"}
                    className="h-7 px-2 text-[12px] capitalize"
                    onClick={() => setView(v)}
                  >
                    {v}
                  </Button>
                ),
              )}
            </div>
          </div>
        }
      />

      <FilterBar
        pills={pills}
        onAddFilter={() =>
          toast.message("Add Filter", {
            description: "Status, severity, or owner.",
          })
        }
        trailing={
          <>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="h-8 w-44 text-[13px] md:w-56"
              aria-label="Search incidents"
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
            <Select value={severity} onValueChange={setSeverity}>
              <SelectTrigger
                size="sm"
                className="w-full max-w-[110px] sm:w-[110px]"
                aria-label="Severity"
              >
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All sev</SelectItem>
                {SEVERITIES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s.toUpperCase()}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={owner} onValueChange={setOwner}>
              <SelectTrigger size="sm" className="w-[130px]" aria-label="Owner">
                <SelectValue placeholder="Owner" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All owners</SelectItem>
                <SelectItem value="unassigned">Unassigned</SelectItem>
                <SelectItem value="sara">@sara</SelectItem>
                <SelectItem value="devon">@devon</SelectItem>
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
          Couldn&apos;t load incidents.
          <div className="mt-3">
            <Button size="sm" onClick={() => setView("success")}>
              Retry
            </Button>
          </div>
        </div>
      ) : view === "empty" || filtered.length === 0 ? (
        <div className="px-1 py-12 text-center">
          <div className="text-[13px] font-medium">
            {view === "empty" ? "No incidents yet" : "No matching incidents"}
          </div>
          <p className="mt-1 text-[13px] text-muted-foreground">
            {view === "empty"
              ? "Create one from a drift alert or + New Incident."
              : "Clear filters or broaden the top-bar time range."}
          </p>
          {view === "empty" && (
            <Button asChild size="sm" className="mt-3" variant="outline">
              <Link href="/dashboard/explore?tab=failures">
                View Explore Failures →
              </Link>
            </Button>
          )}
        </div>
      ) : (
        <IncidentsTable
          rows={pager.slice}
          pager={pager}
          onOpen={(id) => router.push(`/dashboard/incidents/${id}`)}
        />
      )}
    </div>
  )
}

function IncidentsTable({
  rows,
  pager,
  onOpen,
}: {
  rows: IncidentListItem[]
  pager: ReturnType<typeof usePagination<IncidentListItem>>
  onOpen: (id: string) => void
}) {
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Incident</TableHead>
            <TableHead className={listTable.head}>Severity</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Owner</TableHead>
            <TableHead className={listTable.head}>Traces</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Age
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((i) => (
            <TableRow
              key={i.incident_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => onOpen(i.incident_id)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[340px]")}>
                <Link
                  href={`/dashboard/incidents/${i.incident_id}`}
                  className={cn(listTable.primary, "hover:underline")}
                  onClick={(e) => e.stopPropagation()}
                >
                  {i.title}
                </Link>
                <div className={cn(listTable.meta, "mt-0.5 truncate")}>
                  {i.incident_id} · {i.dedupe_key}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot
                  tone={sevTone(i.severity)}
                  label={i.severity.toUpperCase()}
                />
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone={statusTone(i.status)} label={i.status} />
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {i.owner ? (
                  `@${i.owner}`
                ) : (
                  <span className="text-muted-foreground">unassigned</span>
                )}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.mono, "tabular-nums")}
              >
                {i.linked_trace_count}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {i.age}
                <div className="text-[12px]">{i.last_activity}</div>
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
        label="incidents"
        variant="load-more"
      />
    </div>
  )
}

export default function IncidentsPage() {
  return (
    <DashboardShell>
      <IncidentsWorkbench />
    </DashboardShell>
  )
}
