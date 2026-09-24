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
import { DIRECTIVE_LIST } from "@/lib/directives/fixtures"
import type {
  DirectiveLifecycle,
  DirectiveListItem,
  RegressionStatus,
} from "@/lib/directives/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "success"

const STATUSES: DirectiveLifecycle[] = [
  "draft",
  "review",
  "active",
  "deprecated",
  "revoked",
]

function lifeTone(
  s: DirectiveLifecycle,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (s === "active") return "ok"
  if (s === "revoked") return "error"
  if (s === "review") return "warn"
  if (s === "deprecated") return "muted"
  return "info"
}

function regTone(
  s: RegressionStatus,
): "ok" | "error" | "warn" | "muted" | "info" {
  if (s === "passed") return "ok"
  if (s === "failed" || s === "critical_fail") return "error"
  if (s === "pending") return "warn"
  return "muted"
}

function DirectivesWorkbench() {
  const router = useRouter()
  const [view, setView] = React.useState<ViewState>("loading")
  const [q, setQ] = React.useState("")
  const [status, setStatus] = React.useState("all")
  const [owner, setOwner] = React.useState("all")

  React.useEffect(() => {
    const t = window.setTimeout(() => setView("success"), 400)
    return () => window.clearTimeout(t)
  }, [])

  const filtered = React.useMemo(() => {
    return DIRECTIVE_LIST.filter((d) => {
      if (status !== "all" && d.status !== status) return false
      if (owner !== "all" && d.owner !== owner) return false
      if (!q.trim()) return true
      const needle = q.toLowerCase()
      return (
        d.name.toLowerCase().includes(needle) ||
        d.agent.toLowerCase().includes(needle) ||
        d.directive_id.toLowerCase().includes(needle)
      )
    })
  }, [q, status, owner])

  const pager = usePagination(filtered, 15, "accumulate")

  const pills: FilterPill[] = []
  if (status !== "all") {
    pills.push({
      id: "status",
      label: `Status ${status}`,
      onRemove: () => setStatus("all"),
    })
  }
  if (owner !== "all") {
    pills.push({
      id: "owner",
      label: `Owner ${owner}`,
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
        title="Directives"
        description="Preview, approve, promote, and roll back policy safely"
        actions={
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              onClick={() =>
                toast.message("Create directive", {
                  description: "New draft version would open in the editor.",
                })
              }
            >
              + New Directive
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
            description: "Status, owner, or agent.",
          })
        }
        trailing={
          <>
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search…"
              className="h-8 w-44 text-[13px] md:w-56"
              aria-label="Search directives"
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
            <Select value={owner} onValueChange={setOwner}>
              <SelectTrigger size="sm" className="w-[170px]" aria-label="Owner">
                <SelectValue placeholder="Owner" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All owners</SelectItem>
                <SelectItem value="jane@acme.com">jane@acme.com</SelectItem>
                <SelectItem value="devon@acme.com">devon@acme.com</SelectItem>
                <SelectItem value="ops@acme.com">ops@acme.com</SelectItem>
                <SelectItem value="sara@acme.com">sara@acme.com</SelectItem>
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
          Couldn&apos;t load directives.
          <div className="mt-3">
            <Button size="sm" onClick={() => setView("success")}>
              Retry
            </Button>
          </div>
        </div>
      ) : view === "empty" ? (
        <PageEmptyState
          page="directives"
          actionLabel="Create directive"
          onAction={() => router.push("/dashboard/directives")}
        />
      ) : filtered.length === 0 ? (
        <div className="px-1 py-12 text-center">
          <div className="text-[13px] font-medium">No matching directives</div>
          <p className="mt-1 text-[13px] text-muted-foreground">
            Clear filters to broaden results.
          </p>
        </div>
      ) : (
        <DirectivesTable
          rows={pager.slice}
          pager={pager}
          onOpen={(id) => router.push(`/dashboard/directives/${id}`)}
        />
      )}
    </div>
  )
}

function DirectivesTable({
  rows,
  pager,
  onOpen,
}: {
  rows: DirectiveListItem[]
  pager: ReturnType<typeof usePagination<DirectiveListItem>>
  onOpen: (id: string) => void
}) {
  return (
    <div className={listTable.frame}>
      <Table className={listTable.table}>
        <TableHeader>
          <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
            <TableHead className={listTable.head}>Directive</TableHead>
            <TableHead className={listTable.head}>Status</TableHead>
            <TableHead className={listTable.head}>Regression</TableHead>
            <TableHead className={listTable.head}>Version</TableHead>
            <TableHead className={listTable.head}>Rollout</TableHead>
            <TableHead className={cn(listTable.head, "text-right")}>
              Promoted
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((d) => (
            <TableRow
              key={d.directive_id}
              className={cn(listTable.row, "cursor-pointer")}
              onClick={() => onOpen(d.directive_id)}
            >
              <TableCell className={cn(listTable.cell, "max-w-[300px]")}>
                <Link
                  href={`/dashboard/directives/${d.directive_id}`}
                  className={cn(listTable.primary, "hover:underline")}
                  onClick={(e) => e.stopPropagation()}
                >
                  {d.name}
                </Link>
                <div className={cn(listTable.meta, "mt-0.5 truncate")}>
                  {d.agent} · {d.directive_id}
                </div>
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot tone={lifeTone(d.status)} label={d.status} />
              </TableCell>
              <TableCell className={listTable.cell}>
                <StatusDot
                  tone={regTone(d.regression_status)}
                  label={
                    d.regression_status === "not_run"
                      ? "not run"
                      : `${d.scenarios_passed}/${d.scenarios_total}`
                  }
                  detail={
                    d.regression_status !== "not_run"
                      ? d.regression_status
                      : undefined
                  }
                />
              </TableCell>
              <TableCell className={listTable.cell}>
                {d.active_version != null ? (
                  <EnvPill>v{d.active_version}</EnvPill>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell className={listTable.cell}>
                {d.rollout ? (
                  <EnvPill>
                    {d.rollout.percentage}% · {d.rollout.strategy}
                  </EnvPill>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell
                className={cn(listTable.cell, listTable.meta, "text-right")}
              >
                {d.last_promoted_by
                  ? `${d.last_promoted_by.split("@")[0]} · ${d.last_promoted_at?.slice(0, 10)}`
                  : "—"}
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
        label="directives"
        variant="load-more"
      />
    </div>
  )
}

export default function DirectivesPage() {
  return (
    <DashboardShell>
      <DirectivesWorkbench />
    </DashboardShell>
  )
}
