"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { IconX } from "@tabler/icons-react"
import { toast } from "sonner"

import { PaginationBar, usePagination } from "@/components/explore/pagination"
import { listTable } from "@/components/explore/table-styles"
import {
  FilterBar,
  ListPageHeader,
  type FilterPill,
} from "@/components/list/filter-bar"
import { StatusDot } from "@/components/list/status-dot"
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
import {
  DRIFT_ALERT_LIST,
  OPEN_DRIFT_COUNT,
  sortAlertsDefault,
} from "@/lib/drift/fixtures"
import {
  FEATURE_LABEL,
  actionTakenLabel,
  relativeAge,
  severityTone,
  statusTone,
} from "@/lib/drift/labels"
import type {
  DriftAlertListItem,
  DriftAlertStatus,
  DriftSeverity,
} from "@/lib/drift/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "success"

const STATUSES: DriftAlertStatus[] = [
  "open",
  "acknowledged",
  "resolved",
  "false_positive",
]

const SEVERITIES: DriftSeverity[] = ["low", "medium", "high"]

const SHADOW_BANNER_KEY = "ibex.drift.shadow-banner.dismissed"

function DriftWorkbench() {
  const router = useRouter()
  const [view, setView] = React.useState<ViewState>("loading")
  const [q, setQ] = React.useState("")
  const [status, setStatus] = React.useState("open")
  const [severity, setSeverity] = React.useState("all")
  const [agent, setAgent] = React.useState("all")
  const [bannerDismissed, setBannerDismissed] = React.useState(false)

  React.useEffect(() => {
    const t = window.setTimeout(() => setView("success"), 400)
    try {
      if (sessionStorage.getItem(SHADOW_BANNER_KEY) === "1") {
        setBannerDismissed(true)
      }
    } catch {
      /* ignore */
    }
    return () => window.clearTimeout(t)
  }, [])

  const agents = React.useMemo(() => {
    const map = new Map<string, string>()
    for (const a of DRIFT_ALERT_LIST) map.set(a.agent_id, a.agent_name)
    return [...map.entries()]
  }, [])

  const filtered = React.useMemo(() => {
    const rows = DRIFT_ALERT_LIST.filter((a) => {
      if (status !== "all" && a.status !== status) return false
      if (severity !== "all" && a.severity !== severity) return false
      if (agent !== "all" && a.agent_id !== agent) return false
      if (!q.trim()) return true
      const needle = q.toLowerCase()
      return (
        a.alert_id.toLowerCase().includes(needle) ||
        a.agent_name.toLowerCase().includes(needle) ||
        a.agent_slug.toLowerCase().includes(needle) ||
        a.feature_classes.some((f) => f.includes(needle))
      )
    })
    return sortAlertsDefault(rows)
  }, [q, status, severity, agent])

  const pager = usePagination(filtered, 15, "accumulate")

  const openEmpty =
    status === "open" &&
    severity === "all" &&
    agent === "all" &&
    !q.trim() &&
    filtered.length === 0

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
      label: `Severity ${severity}`,
      onRemove: () => setSeverity("all"),
    })
  }
  if (agent !== "all") {
    const name = agents.find(([id]) => id === agent)?.[1] ?? agent
    pills.push({
      id: "agent",
      label: `Agent ${name}`,
      onRemove: () => setAgent("all"),
    })
  }
  if (q.trim()) {
    pills.push({
      id: "q",
      label: `Search ${q.trim()}`,
      onRemove: () => setQ(""),
    })
  }

  const dismissBanner = () => {
    setBannerDismissed(true)
    try {
      sessionStorage.setItem(SHADOW_BANNER_KEY, "1")
    } catch {
      /* ignore */
    }
  }

  return (
    <div className={pagePad}>
      <ListPageHeader
        title="Drift Alerts"
        description="KS / Jensen–Shannon / multi-centroid evidence — Phase 4.5 Intelligence Layer"
        actions={
          <div className="flex items-center gap-2">
            <span className="text-[12px] text-muted-foreground tabular-nums">
              {OPEN_DRIFT_COUNT} open
            </span>
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

      {!bannerDismissed && (
        <div className="mb-3 flex items-start gap-3 rounded-md border border-border/80 bg-muted/40 px-3 py-2.5 text-[12px]">
          <div className="min-w-0 flex-1">
            <div className="font-medium text-foreground">
              Shadow mode is policy — not ignored alerts
            </div>
            <p className="mt-0.5 text-muted-foreground">
              Agents in{" "}
              <span className="text-foreground">
                drift_action_stage = shadow
              </span>{" "}
              log detections only. Rows tagged{" "}
              <span className="text-foreground">
                shadow — no automatic action taken
              </span>{" "}
              are working as designed during the mandatory 30-day shadow window.
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 shrink-0 p-0"
            aria-label="Dismiss shadow banner for this session"
            onClick={dismissBanner}
          >
            <IconX className="size-3.5" />
          </Button>
        </div>
      )}

      <FilterBar
        pills={pills}
        onAddFilter={() =>
          toast.message("Add Filter", {
            description: "Severity, status, agent, or date range.",
          })
        }
        trailing={
          <>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="h-8 w-44 text-[13px] md:w-56"
              aria-label="Search drift alerts"
            />
            <Select value={status} onValueChange={setStatus}>
              <SelectTrigger
                size="sm"
                className="w-full max-w-[140px] sm:w-[140px]"
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
                className="w-full max-w-[120px] sm:w-[120px]"
                aria-label="Severity"
              >
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All severity</SelectItem>
                {SEVERITIES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {s}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={agent} onValueChange={setAgent}>
              <SelectTrigger size="sm" className="w-[150px]" aria-label="Agent">
                <SelectValue placeholder="Agent" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All agents</SelectItem>
                {agents.map(([id, name]) => (
                  <SelectItem key={id} value={id}>
                    {name}
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
          Couldn&apos;t load drift alerts.
          <div className="mt-3">
            <Button size="sm" onClick={() => setView("success")}>
              Retry
            </Button>
          </div>
        </div>
      ) : view === "empty" ? (
        <PageEmptyState page="drift" />
      ) : filtered.length === 0 ? (
        <div className="px-1 py-12 text-center">
          <div className="text-[13px] font-medium">
            {openEmpty ? "No open drift alerts" : "No matching drift alerts"}
          </div>
          <p className="mt-1 mx-auto max-w-md text-[13px] text-muted-foreground">
            {openEmpty
              ? "This is a good state — agents are within baseline. Fingerprints keep computing in the background."
              : "Clear filters or broaden the top-bar time range."}
          </p>
        </div>
      ) : (
        <DriftTable
          rows={pager.slice}
          pager={pager}
          onOpen={(id) => router.push(`/dashboard/drift/${id}`)}
        />
      )}
    </div>
  )
}

function DriftTable({
  rows,
  pager,
  onOpen,
}: {
  rows: DriftAlertListItem[]
  pager: ReturnType<typeof usePagination<DriftAlertListItem>>
  onOpen: (id: string) => void
}) {
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Agent</TableHead>
            <TableHead className={listTable.head}>Severity</TableHead>
            <TableHead className={listTable.head}>Features</TableHead>
            <TableHead className={listTable.head}>Action</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Age
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((a) => (
            <TableRow
              key={a.alert_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => onOpen(a.alert_id)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[260px]")}>
                <Link
                  href={`/dashboard/drift/${a.alert_id}`}
                  className={cn(listTable.primary, "hover:underline")}
                  onClick={(e) => e.stopPropagation()}
                >
                  {a.agent_name}
                </Link>
                <div className={cn(listTable.meta, "mt-0.5 truncate")}>
                  {a.alert_id}
                  {a.drift_action_stage === "shadow" ? (
                    <span className="ml-1.5 text-muted-foreground">
                      · shadow — no automatic action taken
                    </span>
                  ) : null}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone={severityTone(a.severity)} label={a.severity} />
              </TableCell>
              <TableCell className={cn(listTable.cell, "max-w-[280px]")}>
                <div className="truncate text-[12px] text-foreground">
                  {a.feature_classes
                    .map((f) => FEATURE_LABEL[f] ?? f)
                    .join(" · ")}
                </div>
              </TableCell>
              <TableCell className={cn(listTable.cell, listTable.mono)}>
                {actionTakenLabel(a.action_taken)}
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone={statusTone(a.status)} label={a.status} />
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {relativeAge(a.created_at)}
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
        label="alerts"
        variant="load-more"
      />
    </div>
  )
}

export default function DriftAlertsPage() {
  return (
    <DashboardShell>
      <DriftWorkbench />
    </DashboardShell>
  )
}
