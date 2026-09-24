"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"

import {
  ChartSkeleton,
  KpiSkeletonRow,
} from "@/components/charts/chart-skeleton"
import { KpiCard } from "@/components/charts/kpi-card"
import { LatencyPercentileBars } from "@/components/charts/latency-percentile-bars"
import { ModelDistributionBar } from "@/components/charts/model-distribution-bar"
import { RequestsTokensPlot } from "@/components/charts/requests-tokens-plot"
import { listTable } from "@/components/explore/table-styles"
import { ListPageHeader } from "@/components/list/filter-bar"
import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import {
  DashboardShell,
  pagePad,
  panelClass,
} from "@/components/sessions/dashboard-shell"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  AnalyticsApiError,
  getAnalyticsLatency,
  getAnalyticsMemoryPerformance,
  getAnalyticsOverview,
  setAnalyticsDemoFlags,
} from "@/lib/analytics/api"
import {
  AGENT_FILTER_OPTIONS,
  EMPTY_RESULT_WARN_THRESHOLD,
} from "@/lib/analytics/fixtures"
import type {
  AnalyticsLatency,
  AnalyticsMemoryPerformance,
  AnalyticsOverview,
  AnalyticsPeriod,
  TopAgentRow,
} from "@/lib/analytics/types"
import { cn } from "@/lib/utils"

type ViewState = "loading" | "empty" | "error" | "forbidden" | "success"

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
})
const full = new Intl.NumberFormat("en-US")
const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
})

function AnalyticsWorkbench() {
  const [period] = React.useState<AnalyticsPeriod>("7d")
  const [agentIds, setAgentIds] = React.useState<string[]>([])
  const [view, setView] = React.useState<ViewState>("loading")
  const [errorMsg, setErrorMsg] = React.useState<string | null>(null)
  const [overview, setOverview] = React.useState<AnalyticsOverview | null>(null)
  const [latency, setLatency] = React.useState<AnalyticsLatency | null>(null)
  const [memory, setMemory] = React.useState<AnalyticsMemoryPerformance | null>(
    null,
  )

  const load = React.useCallback(async () => {
    setView("loading")
    setErrorMsg(null)
    try {
      const [o, l, m] = await Promise.all([
        getAnalyticsOverview({ period, agentIds }),
        getAnalyticsLatency({ period }),
        getAnalyticsMemoryPerformance({ period }),
      ])
      if (o.total_requests === 0) {
        setOverview(o)
        setLatency(l)
        setMemory(m)
        setView("empty")
        return
      }
      setOverview(o)
      setLatency(l)
      setMemory(m)
      setView("success")
    } catch (e) {
      if (e instanceof AnalyticsApiError && e.code === "FORBIDDEN") {
        setErrorMsg(e.message)
        setView("forbidden")
        return
      }
      setErrorMsg(e instanceof Error ? e.message : "Request failed")
      setView("error")
    }
  }, [period, agentIds])

  React.useEffect(() => {
    void load()
  }, [load])

  const setDemo = (next: ViewState) => {
    setAnalyticsDemoFlags({
      forbidden: next === "forbidden",
      empty: next === "empty",
      fail: next === "error",
    })
    if (next === "loading") {
      setView("loading")
      window.setTimeout(() => void load(), 50)
      return
    }
    void load()
  }

  const toggleAgent = (id: string) => {
    setAgentIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    )
  }

  return (
    <div className={pagePad}>
      <ListPageHeader
        title="Analytics"
        description="trace:read · ClickHouse usage_facts · estimated cost is advisory"
        actions={
          <div className="flex flex-wrap items-center gap-1">
            {(
              [
                "loading",
                "empty",
                "error",
                "forbidden",
                "success",
              ] as ViewState[]
            ).map((v) => (
              <Button
                key={v}
                size="sm"
                variant={view === v ? "default" : "ghost"}
                className="h-7 px-2 text-[12px] capitalize"
                onClick={() => setDemo(v)}
              >
                {v}
              </Button>
            ))}
          </div>
        }
      />

      {/* Agent filter — time range is the global header control */}
      <div className="mb-4 flex flex-wrap items-center gap-2 border-b border-border/60 pb-3">
        <Select
          value={agentIds[0] ?? "all"}
          onValueChange={(v) => {
            if (v === "all" || v == null) setAgentIds([])
            else setAgentIds([v])
          }}
        >
          <SelectTrigger
            size="sm"
            className="w-full max-w-[200px] sm:w-[180px]"
            aria-label="Agent filter"
          >
            <SelectValue placeholder="All agents" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All agents</SelectItem>
            {AGENT_FILTER_OPTIONS.map((a) => (
              <SelectItem key={a.id} value={a.id}>
                {a.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {agentIds.length > 1 ? (
          <span className="text-[12px] text-muted-foreground">
            +{agentIds.length - 1} more
          </span>
        ) : null}
        <div className="ml-auto flex flex-wrap gap-1">
          {AGENT_FILTER_OPTIONS.slice(0, 4).map((a) => {
            const on = agentIds.includes(a.id)
            return (
              <button
                key={a.id}
                type="button"
                onClick={() => toggleAgent(a.id)}
                className={cn(
                  "h-7 rounded-md border px-2 text-[11px]",
                  on
                    ? "border-foreground bg-muted text-foreground"
                    : "border-border text-muted-foreground hover:text-foreground",
                )}
              >
                {a.slug}
              </button>
            )
          })}
        </div>
      </div>

      {view === "loading" ? (
        <div className="space-y-4">
          <KpiSkeletonRow />
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card className={panelClass}>
              <CardContent className="px-4 py-4">
                <ChartSkeleton height={260} />
              </CardContent>
            </Card>
            <Card className={panelClass}>
              <CardContent className="px-4 py-4">
                <ChartSkeleton height={200} />
              </CardContent>
            </Card>
          </div>
          <ChartSkeleton height={160} />
        </div>
      ) : null}

      {view === "forbidden" ? (
        <ErrorPanel
          title="Insufficient permission"
          body={
            errorMsg ??
            "Analytics requires trace:read. There is no separate analytics-only bit."
          }
          onRetry={() => setDemo("success")}
        />
      ) : null}

      {view === "error" ? (
        <ErrorPanel
          title="Analytics endpoint failed"
          body={
            errorMsg ??
            "Could not load overview / latency / memory-performance."
          }
          onRetry={() => setDemo("success")}
        />
      ) : null}

      {view === "empty" ? (
        <PageEmptyState page="analytics" />
      ) : null}

      {view === "success" && overview && latency && memory ? (
        <div className="space-y-4">
          <KpiRow overview={overview} period={period} />

          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
            <Card className={panelClass}>
              <CardHeader className="border-b border-border/60 px-4 py-3">
                <CardTitle className="text-[13px] font-medium">
                  Requests / tokens over time
                </CardTitle>
                <p className="text-[12px] text-muted-foreground">
                  toStartOfHour(occurred_at) · MetricTrend panels · matches
                  _SQL_ORG_TIME
                </p>
              </CardHeader>
              <CardContent className="px-3 py-3">
                <RequestsTokensPlot series={overview.series} />
              </CardContent>
            </Card>

            <Card className={panelClass}>
              <CardHeader className="border-b border-border/60 px-4 py-3">
                <CardTitle className="text-[13px] font-medium">
                  Model distribution
                </CardTitle>
                <p className="text-[12px] text-muted-foreground">
                  Top {5} + Other · mono labels
                </p>
              </CardHeader>
              <CardContent className="px-4 py-3">
                <ModelDistributionBar
                  distribution={overview.model_distribution}
                />
              </CardContent>
            </Card>
          </div>

          <TopAgentsTable
            rows={overview.top_agents}
            period={period}
            agentIds={agentIds}
          />

          <Card className={panelClass}>
            <CardHeader className="border-b border-border/60 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <CardTitle className="text-[13px] font-medium">
                    Latency breakdown
                  </CardTitle>
                  <p className="text-[12px] text-muted-foreground">
                    proxy · context · auth · rate limit · provider — p50 / p95 /
                    p99
                  </p>
                </div>
                {latency.completeness === "partial" ? (
                  <span className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-400">
                    partial data
                  </span>
                ) : null}
              </div>
            </CardHeader>
            <CardContent className="px-4 py-3">
              <LatencyPercentileBars stages={latency.stages} />
            </CardContent>
          </Card>

          <SlowRequestsTable rows={latency.slow_requests} />

          <MemoryPerformanceSection memory={memory} />
        </div>
      ) : null}
    </div>
  )
}

function KpiRow({
  overview,
  period,
}: {
  overview: AnalyticsOverview
  period: AnalyticsPeriod
}) {
  const partial = (field: (typeof overview.partial_fields)[number]) =>
    overview.partial_fields.includes(field)

  return (
    <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
      <KpiCard
        label="Requests"
        value={compact.format(overview.total_requests)}
        deltaPct={overview.requests_change_pct}
        higherIsBetter
        hint={`vs prior ${period}`}
        partial={partial("total_requests")}
      />
      <KpiCard
        label="Tokens"
        value={compact.format(overview.total_tokens)}
        deltaPct={overview.tokens_change_pct}
        higherIsBetter
        hint={`vs prior ${period}`}
        partial={partial("total_tokens")}
      />
      <KpiCard
        label="Sessions"
        value={full.format(overview.total_sessions)}
        deltaPct={overview.sessions_change_pct}
        higherIsBetter
        hint={`vs prior ${period}`}
      />
      <KpiCard
        label="Error rate"
        value={`${(overview.error_rate * 100).toFixed(2)}%`}
        deltaPct={overview.error_rate_change_pct}
        higherIsBetter={false}
        hint={`vs prior ${period}`}
        partial={partial("error_rate")}
      />
      <KpiCard
        label="Est. cost"
        value={usd.format(overview.estimated_cost_usd)}
        deltaPct={overview.cost_change_pct}
        higherIsBetter={false}
        hint="advisory · not ledger"
        partial={partial("estimated_cost_usd")}
        mutedValue
      />
    </div>
  )
}

function TopAgentsTable({
  rows,
  period,
  agentIds,
}: {
  rows: TopAgentRow[]
  period: AnalyticsPeriod
  agentIds: string[]
}) {
  const router = useRouter()
  const [sort, setSort] = React.useState<"request_count" | "token_count">(
    "request_count",
  )
  const sorted = React.useMemo(
    () => [...rows].sort((a, b) => b[sort] - a[sort]),
    [rows, sort],
  )

  const hrefFor = (id: string) => {
    const params = new URLSearchParams()
    params.set("period", period)
    if (agentIds.length) params.set("agents", agentIds.join(","))
    return `/dashboard/agents/${id}?${params.toString()}`
  }

  return (
    <Card className={panelClass}>
      <CardHeader className="border-b border-border/60 px-4 py-3">
        <CardTitle className="text-[13px] font-medium">Top agents</CardTitle>
        <p className="text-[12px] text-muted-foreground">
          Sortable request_count / token_count · row → Agent Detail
        </p>
      </CardHeader>
      <CardContent className="px-0 py-0">
        <Table className={listTable.table}>
          <TableHeader>
            <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
              <TableHead className={listTable.head}>Agent</TableHead>
              <TableHead className={listTable.head}>
                <button
                  type="button"
                  className={cn(
                    "hover:text-foreground",
                    sort === "request_count" && "text-foreground",
                  )}
                  onClick={() => setSort("request_count")}
                >
                  request_count{sort === "request_count" ? " ↓" : ""}
                </button>
              </TableHead>
              <TableHead className={cn(listTable.head, "text-right")}>
                <button
                  type="button"
                  className={cn(
                    "hover:text-foreground",
                    sort === "token_count" && "text-foreground",
                  )}
                  onClick={() => setSort("token_count")}
                >
                  token_count{sort === "token_count" ? " ↓" : ""}
                </button>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {sorted.map((a) => (
              <TableRow
                key={a.agent_id}
                className={cn(listTable.row, "cursor-pointer")}
                onClick={() => router.push(hrefFor(a.agent_id))}
              >
                <TableCell className={listTable.cell}>
                  <Link
                    href={hrefFor(a.agent_id)}
                    className={cn(listTable.primary, "hover:underline")}
                    onClick={(e) => e.stopPropagation()}
                  >
                    {a.name}
                  </Link>
                  <div className={listTable.meta}>{a.slug}</div>
                </TableCell>
                <TableCell
                  className={cn(listTable.cell, listTable.mono, "tabular-nums")}
                >
                  {full.format(a.request_count)}
                </TableCell>
                <TableCell
                  className={cn(
                    listTable.cell,
                    listTable.mono,
                    "text-right tabular-nums",
                  )}
                >
                  {compact.format(a.token_count)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function SlowRequestsTable({
  rows,
}: {
  rows: AnalyticsLatency["slow_requests"]
}) {
  return (
    <Card className={panelClass}>
      <CardHeader className="border-b border-border/60 px-4 py-3">
        <CardTitle className="text-[13px] font-medium">Slow requests</CardTitle>
        <p className="text-[12px] text-muted-foreground">
          Row → Trace Inspector (4.D.2) — not a modal
        </p>
      </CardHeader>
      <CardContent className="px-0 py-0">
        <Table className={listTable.table}>
          <TableHeader>
            <TableRow className={cn(listTable.headRow, "hover:bg-transparent")}>
              <TableHead className={listTable.head}>trace_id</TableHead>
              <TableHead className={listTable.head}>total</TableHead>
              <TableHead className={listTable.head}>provider</TableHead>
              <TableHead className={listTable.head}>context</TableHead>
              <TableHead className={cn(listTable.head, "text-right")}>
                timestamp
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.trace_id} className={listTable.row}>
                <TableCell className={listTable.cell}>
                  <Link
                    href={`/dashboard/explore/t/${r.trace_id}`}
                    className={cn(
                      listTable.mono,
                      "text-foreground hover:underline",
                    )}
                  >
                    {r.trace_id}
                  </Link>
                  <div className={listTable.meta}>{r.agent_slug}</div>
                </TableCell>
                <TableCell
                  className={cn(listTable.cell, listTable.mono, "tabular-nums")}
                >
                  {r.total_latency_ms}ms
                </TableCell>
                <TableCell
                  className={cn(listTable.cell, listTable.mono, "tabular-nums")}
                >
                  {r.provider_latency_ms}ms
                </TableCell>
                <TableCell
                  className={cn(listTable.cell, listTable.mono, "tabular-nums")}
                >
                  {r.context_assembly_ms}ms
                </TableCell>
                <TableCell
                  className={cn(
                    listTable.cell,
                    listTable.meta,
                    "text-right font-mono",
                  )}
                >
                  {r.timestamp.replace("T", " ").slice(0, 16)}Z
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

function MemoryPerformanceSection({
  memory,
}: {
  memory: AnalyticsMemoryPerformance
}) {
  const emptyWarn =
    memory.retrieval_stats.empty_result_rate >= EMPTY_RESULT_WARN_THRESHOLD
  const r = memory.retrieval_stats
  const q = memory.quality_stats

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-2">
        <Card className={panelClass}>
          <CardHeader className="border-b border-border/60 px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Retrieval stats
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 px-4 py-3">
            <Stat
              label="total_retrievals"
              value={compact.format(r.total_retrievals)}
            />
            <Stat
              label="avg_memories_per_request"
              value={r.avg_memories_per_request.toFixed(1)}
            />
            <Stat
              label="avg_retrieval_latency_ms"
              value={`${r.avg_retrieval_latency_ms}ms`}
            />
            <Stat
              label="cache_hit_rate"
              value={`${(r.cache_hit_rate * 100).toFixed(0)}%`}
            />
            <div className="col-span-2">
              <div className="text-[11px] text-muted-foreground">
                empty_result_rate
              </div>
              <div
                className={cn(
                  "mt-0.5 font-mono text-[18px] tabular-nums",
                  emptyWarn
                    ? "text-amber-700 dark:text-amber-400"
                    : "text-foreground",
                )}
              >
                {(r.empty_result_rate * 100).toFixed(1)}%
                {emptyWarn ? (
                  <span className="ml-2 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-sans">
                    above {EMPTY_RESULT_WARN_THRESHOLD * 100}% warn
                  </span>
                ) : null}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className={panelClass}>
          <CardHeader className="border-b border-border/60 px-4 py-3">
            <CardTitle className="text-[13px] font-medium">
              Quality stats
            </CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3 px-4 py-3">
            <Stat
              label="avg_relevance_score"
              value={q.avg_relevance_score.toFixed(2)}
            />
            <Stat
              label="positive_feedback_rate"
              value={`${(q.positive_feedback_rate * 100).toFixed(0)}%`}
            />
            <Stat
              label="negative_feedback_rate"
              value={`${(q.negative_feedback_rate * 100).toFixed(0)}%`}
            />
          </CardContent>
        </Card>
      </div>

      <Card className={panelClass}>
        <CardHeader className="border-b border-border/60 px-4 py-3">
          <CardTitle className="text-[13px] font-medium">
            Top retrieved memories
          </CardTitle>
          <p className="text-[12px] text-muted-foreground">
            Row → Memory Detail (4.D.3)
          </p>
        </CardHeader>
        <CardContent className="px-0 py-0">
          <Table className={listTable.table}>
            <TableHeader>
              <TableRow
                className={cn(listTable.headRow, "hover:bg-transparent")}
              >
                <TableHead className={listTable.head}>Memory</TableHead>
                <TableHead className={listTable.head}>retrievals</TableHead>
                <TableHead className={cn(listTable.head, "text-right")}>
                  avg_score
                </TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {memory.top_retrieved_memories.map((m) => (
                <TableRow key={m.memory_id} className={listTable.row}>
                  <TableCell className={cn(listTable.cell, "max-w-[360px]")}>
                    <Link
                      href={`/dashboard/memories/${m.memory_id}`}
                      className={cn(listTable.primary, "hover:underline")}
                    >
                      {m.memory_id}
                    </Link>
                    <div className={cn(listTable.meta, "truncate")}>
                      {m.content_preview}
                    </div>
                  </TableCell>
                  <TableCell
                    className={cn(
                      listTable.cell,
                      listTable.mono,
                      "tabular-nums",
                    )}
                  >
                    {full.format(m.retrieval_count)}
                  </TableCell>
                  <TableCell
                    className={cn(
                      listTable.cell,
                      listTable.mono,
                      "text-right tabular-nums",
                    )}
                  >
                    {m.avg_score.toFixed(2)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 font-mono text-[16px] tabular-nums text-foreground">
        {value}
      </div>
    </div>
  )
}

function ErrorPanel({
  title,
  body,
  onRetry,
}: {
  title: string
  body: string
  onRetry: () => void
}) {
  return (
    <div className="rounded-lg border border-border/70 px-4 py-12 text-center">
      <div className="text-[14px] font-medium">{title}</div>
      <p className="mx-auto mt-1 max-w-md text-[13px] text-muted-foreground">
        {body}
      </p>
      <Button size="sm" className="mt-4" onClick={onRetry}>
        Retry
      </Button>
    </div>
  )
}

export default function AnalyticsPage() {
  return (
    <DashboardShell>
      <AnalyticsWorkbench />
    </DashboardShell>
  )
}
