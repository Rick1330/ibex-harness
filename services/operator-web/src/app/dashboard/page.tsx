"use client"

import * as React from "react"
import {
  IconAlertCircle,
  IconArrowDownRight,
  IconArrowUpRight,
  IconDownload,
  IconPlugConnected,
  IconPlus,
  IconRefresh,
  IconUserPlus,
} from "@tabler/icons-react"

import {
  ChartLegendSwatch,
  MetricTrend,
  MetricTrendGrid,
} from "@/components/charts/metric-trend"
import {
  DashboardShell,
  pagePad,
  panelClass as panelBase,
} from "@/components/sessions/dashboard-shell"
import { OnboardingChecklist } from "@/components/onboarding/onboarding-checklist"
import { useOnboarding } from "@/components/onboarding/onboarding-provider"
import { PageEmptyState } from "@/components/onboarding/page-empty-state"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { FRESHNESS_TONE, SHELL_HEALTH } from "@/lib/shell-health"

const panelClass = `${panelBase} gap-4 py-4`

// ---------------------------------------------------------------------------
// Design fixtures — shapes mirror documented contracts. Shell health now
// models /ready + SSE drain (see SHELL_HEALTH); analytics remain fixture data.
// ---------------------------------------------------------------------------

type ViewState = "loading" | "empty" | "error" | "success"

const mockSummary = {
  total_requests: 1284092,
  total_tokens: 48200000,
  error_rate: 0.018,
  p95_total_latency_ms: 412,
  estimated_cost_usd: 1284.55,
  total_sessions: 8431,
  total_memories_created: 12908,
  top_agents: [
    { name: "support-agent", request_count: 45210, token_count: 12400000 },
    { name: "billing-bot", request_count: 12100, token_count: 3100000 },
    { name: "docs-helper", request_count: 8430, token_count: 1900000 },
    { name: "triage", request_count: 5120, token_count: 1100000 },
    { name: "scheduler", request_count: 2980, token_count: 600000 },
  ],
  model_distribution: [
    { model: "gpt-4-turbo", share: 0.65, className: "bg-chart-2" },
    { model: "gpt-3.5-turbo", share: 0.25, className: "bg-chart-4" },
    { model: "claude-3-opus", share: 0.1, className: "bg-chart-5" },
  ],
}

const mockTrends = {
  requests_change_pct: 12.4,
  tokens_change_pct: 8.1,
  error_rate_change_pct: -12.0,
}

const mockTrendSeries = [
  { hour: "00:00", requests: 2120, errors: 31, expected: 2280 },
  { hour: "02:00", requests: 2860, errors: 38, expected: 2440 },
  { hour: "04:00", requests: 2490, errors: 29, expected: 2600 },
  { hour: "06:00", requests: 3120, errors: 42, expected: 2780 },
  { hour: "08:00", requests: 4860, errors: 55, expected: 3640 },
  { hour: "10:00", requests: 5410, errors: 92, expected: 4380 },
  { hour: "12:00", requests: 4380, errors: 71, expected: 4620 },
  { hour: "14:00", requests: 5120, errors: 66, expected: 4860 },
  { hour: "16:00", requests: 6720, errors: 119, expected: 5320 },
  { hour: "18:00", requests: 6280, errors: 88, expected: 5740 },
  { hour: "20:00", requests: 7010, errors: 76, expected: 6120 },
  { hour: "Now", requests: 8420, errors: 141, expected: 6480 },
]

const mockLatency = [
  { name: "proxy_overhead", p50: 12, p95: 28, p99: 67 },
  { name: "context_assembly", p50: 35, p95: 52, p99: 89 },
  { name: "auth_validation", p50: 0.8, p95: 1.2, p99: 2 },
]

const mockChecks = [
  { name: "postgres", status: "ok", latency_ms: 3 },
  { name: "redis", status: "ok", latency_ms: 1 },
  { name: "clickhouse", status: "ok", latency_ms: 12 },
  { name: "sse_drain", status: "ok", latency_ms: 4 },
]

const mockActivity = [
  {
    time: "2m",
    title: "Directive v12 promoted",
    href: "/dashboard/directives/dir_support_refund",
  },
  {
    time: "14m",
    title: "Incident SEV1 checkout opened",
    href: "/dashboard/incidents/inc_7f2a",
  },
  { time: "41m", title: "Export bundle ready", href: "#" },
  { time: "1h", title: "New session batch", meta: "312 sessions", href: "#" },
]

const compact = new Intl.NumberFormat("en-US", { notation: "compact" })
const full = new Intl.NumberFormat("en-US")

type SecondaryMetric =
  | {
      label: string
      value: string
      delta: number
      higherIsBetter: boolean
    }
  | {
      label: string
      value: string
      hint: string
    }

function useCountUp(value: number, duration = 900) {
  const [display, setDisplay] = React.useState(0)
  const hasRun = React.useRef(false)

  React.useEffect(() => {
    if (hasRun.current) {
      return
    }

    hasRun.current = true
    let frame = 0

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      frame = window.requestAnimationFrame(() => setDisplay(value))
      return () => window.cancelAnimationFrame(frame)
    }

    const started = performance.now()

    const tick = (now: number) => {
      const progress = Math.min((now - started) / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(Math.round(value * eased))

      if (progress < 1) {
        frame = window.requestAnimationFrame(tick)
      }
    }

    frame = window.requestAnimationFrame(tick)

    return () => window.cancelAnimationFrame(frame)
  }, [duration, value])

  return display
}

function Delta({
  value,
  higherIsBetter,
}: {
  value: number
  higherIsBetter: boolean
}) {
  const good = higherIsBetter ? value >= 0 : value <= 0

  return (
    <span
      className={
        good
          ? "inline-flex items-center gap-1 font-medium text-foreground tabular-nums"
          : "inline-flex items-center gap-1 font-medium text-destructive tabular-nums"
      }
    >
      {value >= 0 ? (
        <IconArrowUpRight className="size-3.5" aria-hidden />
      ) : (
        <IconArrowDownRight className="size-3.5" aria-hidden />
      )}
      {value >= 0 ? "+" : ""}
      {value.toFixed(1)}%
    </span>
  )
}

function HeroMetricStrip({ period }: { period: string }) {
  const requests = useCountUp(mockSummary.total_requests)
  const secondary: SecondaryMetric[] = [
    {
      label: "Tokens",
      value: compact.format(mockSummary.total_tokens),
      delta: mockTrends.tokens_change_pct,
      higherIsBetter: true,
    },
    {
      label: "Sessions",
      value: full.format(mockSummary.total_sessions),
      hint: period,
    },
    {
      label: "Error rate",
      value: `${(mockSummary.error_rate * 100).toFixed(1)}%`,
      delta: mockTrends.error_rate_change_pct,
      higherIsBetter: false,
    },
    {
      label: "p95 latency",
      value: `${mockSummary.p95_total_latency_ms}ms`,
      hint: "end to end",
    },
    {
      label: "Est. cost",
      value: `$${mockSummary.estimated_cost_usd.toLocaleString("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })}`,
      hint: "advisory",
    },
  ]

  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "0ms" }}>
      <CardHeader className="gap-5">
        <div className="flex flex-wrap items-center gap-2">
          <CardDescription className="font-mono text-[12px] uppercase tracking-[0.18em]">
            At a glance
          </CardDescription>
          <span className="ml-auto rounded-full border px-2 py-0.5 font-mono text-[12px] text-muted-foreground">
            {period}
          </span>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <CardDescription>Total requests</CardDescription>
            <CardTitle className="mt-2 font-serif text-5xl font-normal tracking-normal tabular-nums md:text-7xl">
              {full.format(requests)}
            </CardTitle>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <Delta value={mockTrends.requests_change_pct} higherIsBetter />
            <span className="text-muted-foreground">vs prior {period}</span>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 border-t pt-5 sm:grid-cols-2 lg:grid-cols-5">
          {secondary.map((item) => (
            <div key={item.label} className="min-w-0">
              <div className="text-xs text-muted-foreground">{item.label}</div>
              <div className="mt-1 font-mono text-xl font-medium tabular-nums">
                {item.value}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {"delta" in item ? (
                  <Delta
                    value={item.delta}
                    higherIsBetter={item.higherIsBetter}
                  />
                ) : (
                  item.hint
                )}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function SystemsStrip() {
  const health = SHELL_HEALTH
  const tone = FRESHNESS_TONE[health.freshness]
  return (
    <Card className={panelClass}>
      <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3">
        <span className="flex items-center gap-2 text-sm font-medium">
          <span className={`size-2 rounded-full ${tone.dot}`} />
          {health.freshness} · {health.connection}
        </span>
        {mockChecks.map((c) => (
          <span
            key={c.name}
            className="flex items-center gap-1.5 text-xs text-muted-foreground"
            title={`${c.name}: status=${c.status}, latency=${c.latency_ms}ms`}
          >
            <span className="size-1.5 rounded-full bg-muted-foreground" />
            <span className="font-mono">{c.name}</span>
            <span className="tabular-nums">{c.latency_ms}ms</span>
          </span>
        ))}
        <span
          className="ml-auto text-[12px] text-muted-foreground"
          title={health.detail}
        >
          /ready + SSE · lag {health.lag_ms ?? "—"}ms · last sync just now
        </span>
      </CardContent>
    </Card>
  )
}

function TrendPanel() {
  const series = mockTrendSeries.map((d) => ({
    t: d.hour,
    requests: d.requests,
    expected: d.expected,
    errors: d.errors,
  }))
  const now = series[series.length - 1]

  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "60ms" }}>
      <CardHeader>
        <div>
          <CardTitle>Request volume & errors</CardTitle>
          <CardDescription>
            Fingerprint-style scalar trends — expected band as reference,
            anomaly marked on the current hour.
          </CardDescription>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <MetricTrendGrid>
          <MetricTrend
            title="requests"
            data={series}
            dataKey="requests"
            secondaryKey="expected"
            baseline={6500}
            baselineLabel="band"
            highlightX="Now"
            marks={
              now
                ? [{ x: "Now", y: now.requests, tone: "destructive" }]
                : undefined
            }
            height={160}
            yFormatter={(v) => compact.format(v)}
            config={{
              value: { label: "Requests", color: "var(--foreground)" },
              secondary: {
                label: "Expected",
                color: "var(--muted-foreground)",
              },
            }}
          />
          <MetricTrend
            title="errors"
            data={series}
            dataKey="errors"
            highlightX="Now"
            marks={
              now ? [{ x: "Now", y: now.errors, tone: "amber" }] : undefined
            }
            height={160}
            config={{
              value: { label: "Errors", color: "var(--foreground)" },
            }}
          />
        </MetricTrendGrid>
        <div className="flex flex-wrap gap-4">
          <ChartLegendSwatch
            className="border-dashed border-muted-foreground"
            label="Expected / band"
          />
          <ChartLegendSwatch className="bg-foreground" label="Observed" />
          <ChartLegendSwatch className="bg-destructive" label="Anomaly" />
        </div>
      </CardContent>
    </Card>
  )
}

function LatencyPanel() {
  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "120ms" }}>
      <CardHeader>
        <CardTitle>Latency breakdown</CardTitle>
        <CardDescription>
          p50 / p95 / p99 per stage — same metric-panel language as drift
          fingerprints
        </CardDescription>
      </CardHeader>
      <CardContent>
        <MetricTrendGrid>
          {mockLatency.map((r) => (
            <MetricTrend
              key={r.name}
              title={r.name}
              data={[
                { t: "p50", value: r.p50 },
                { t: "p95", value: r.p95 },
                { t: "p99", value: r.p99 },
              ]}
              dataKey="value"
              referenceY={r.p95}
              referenceYLabel="p95"
              height={120}
              yFormatter={(v) => `${v}`}
              marks={[{ x: "p99", y: r.p99, tone: "amber" }]}
            />
          ))}
        </MetricTrendGrid>
      </CardContent>
    </Card>
  )
}

function TopAgentsPanel() {
  const max = Math.max(...mockSummary.top_agents.map((a) => a.request_count))

  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "180ms" }}>
      <CardHeader>
        <CardTitle>Top agents</CardTitle>
        <CardDescription>By request count in period</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {mockSummary.top_agents.map((a, i) => (
          <a
            key={a.name}
            href={`/dashboard/agents?q=${encodeURIComponent(a.name)}`}
            className="grid grid-cols-[1.5rem_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted"
          >
            <span className="w-4 text-xs text-muted-foreground tabular-nums">
              {i + 1}
            </span>
            <span className="min-w-0">
              <span className="block truncate font-mono text-[13px] font-medium">
                {a.name}
              </span>
              <span className="mt-1 block h-1.5 overflow-hidden rounded-sm bg-muted">
                <span
                  className="block h-full rounded-sm bg-foreground"
                  style={{ width: `${(a.request_count / max) * 100}%` }}
                />
              </span>
            </span>
            <span className="ml-auto text-xs text-muted-foreground tabular-nums">
              {compact.format(a.request_count)} req ·{" "}
              {compact.format(a.token_count)} tok
            </span>
          </a>
        ))}
      </CardContent>
    </Card>
  )
}

function ModelDistributionPanel() {
  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "240ms" }}>
      <CardHeader>
        <CardTitle>Model distribution</CardTitle>
        <CardDescription>Share of requests by model</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div
          className="flex h-3 w-full overflow-hidden rounded-sm"
          role="img"
          aria-label="Model share: gpt-4-turbo 65%, gpt-3.5-turbo 25%, claude-3-opus 10%"
        >
          {mockSummary.model_distribution.map((m) => (
            <div
              key={m.model}
              className={m.className}
              style={{ width: `${m.share * 100}%` }}
            />
          ))}
        </div>
        <div className="flex flex-col gap-1.5">
          {mockSummary.model_distribution.map((m) => (
            <div key={m.model} className="flex items-center gap-2 text-sm">
              <span className={`size-2.5 rounded-[2px] ${m.className}`} />
              <span className="font-mono text-[13px]">{m.model}</span>
              <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                {(m.share * 100).toFixed(0)}%
              </span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function RecentActivityPanel() {
  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "300ms" }}>
      <CardHeader>
        <CardTitle>Recent activity</CardTitle>
        <CardDescription>Operational changes in this workspace</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-1">
        {mockActivity.map((item) => (
          <a
            key={`${item.time}-${item.title}`}
            href={item.href}
            className="grid grid-cols-[3rem_minmax(0,1fr)_auto] items-center gap-3 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted"
          >
            <span className="font-mono text-xs text-muted-foreground tabular-nums">
              {item.time}
            </span>
            <span className="min-w-0 truncate">{item.title}</span>
            <span className="font-mono text-[12px] text-muted-foreground">
              {item.meta ?? "view"}
            </span>
          </a>
        ))}
      </CardContent>
    </Card>
  )
}

function OverviewSkeletons() {
  return (
    <div className="flex flex-col gap-4 md:gap-6">
      <Skeleton className="h-9 w-56" />
      <Skeleton className="h-[258px] w-full rounded-lg" />
      <Skeleton className="h-[392px] w-full rounded-lg" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-[280px] w-full rounded-lg" />
        <Skeleton className="h-[280px] w-full rounded-lg" />
      </div>
    </div>
  )
}

function OverviewEmpty() {
  return <PageEmptyState page="overview" actionLabel="Send a test request" />
}

function OverviewError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className={panelClass}>
      <CardContent className="flex flex-col items-center gap-2 py-12 text-center">
        <IconAlertCircle className="size-8 text-destructive" aria-hidden />
        <div className="text-base font-medium">Couldn&apos;t load overview</div>
        <p className="max-w-sm text-sm text-muted-foreground">
          <span className="font-mono text-[13px]">
            GET /v1/analytics/overview
          </span>{" "}
          failed. No partial or stale cards are shown — retry to reload the
          whole page state.
        </p>
        <Button size="sm" className="mt-2" onClick={onRetry}>
          <IconRefresh />
          Retry
        </Button>
      </CardContent>
    </Card>
  )
}

function OverviewWorkbench() {
  const {
    showChecklist,
    agentCount,
    demoZeroAgents,
    setDemoZeroAgents,
    resetOnboarding,
    requiredComplete,
  } = useOnboarding()
  const [view, setView] = React.useState<ViewState>("loading")
  const period = "24h"
  const locked = React.useRef(false)
  const timers = React.useRef<number[]>([])

  const later = React.useCallback((fn: () => void, ms: number) => {
    timers.current.push(window.setTimeout(fn, ms))
  }, [])

  React.useEffect(() => {
    later(() => {
      if (!locked.current) {
        // Zero agents → empty overview (honest first-run), else success fixtures.
        setView(agentCount === 0 ? "empty" : "success")
      }
    }, 600)
    const stash = timers.current
    return () => stash.forEach((t) => window.clearTimeout(t))
  }, [later, agentCount])

  React.useEffect(() => {
    if (typeof window === "undefined") return
    if (window.location.hash === "#onboarding" && showChecklist) {
      document
        .getElementById("onboarding")
        ?.scrollIntoView({ behavior: "smooth", block: "start" })
    }
  }, [showChecklist])

  const preview = (v: ViewState) => {
    locked.current = true
    setView(v)
  }

  return (
    <div className="@container/main flex flex-1 flex-col gap-2">
      <div className={`${pagePad} md:gap-4`}>
        <div id="onboarding">
          <OnboardingChecklist />
        </div>

        {view === "loading" ? (
          <OverviewSkeletons />
        ) : (
          <>
            <div className="flex flex-wrap items-center justify-end gap-1">
              <Button
                size="sm"
                variant={demoZeroAgents ? "default" : "ghost"}
                className="h-7 px-2 text-[11px]"
                onClick={() => setDemoZeroAgents(!demoZeroAgents)}
              >
                {demoZeroAgents ? "Exit first-run" : "First-run demo"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-[11px]"
                onClick={resetOnboarding}
              >
                Reset checklist
              </Button>
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

            {view === "empty" ? (
              <>
                {!showChecklist ? (
                  <PageEmptyState
                    page="overview"
                    actionLabel="Open setup guide"
                  />
                ) : (
                  <OverviewEmpty />
                )}
              </>
            ) : view === "error" ? (
              <OverviewError
                onRetry={() => {
                  locked.current = true
                  setView("loading")
                  later(
                    () => setView(agentCount === 0 ? "empty" : "success"),
                    1000,
                  )
                }}
              />
            ) : (
              <>
                {!requiredComplete ? (
                  <p className="text-[11px] text-muted-foreground">
                    Fixture metrics shown for the populated org — finish the
                    setup guide before treating these as live.
                  </p>
                ) : null}
                <SystemsStrip />
                <HeroMetricStrip period={period} />
                <TrendPanel />
                <div className="grid gap-4 lg:grid-cols-2">
                  <LatencyPanel />
                  <TopAgentsPanel />
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <ModelDistributionPanel />
                  <RecentActivityPanel />
                </div>
                <div
                  className="rise flex flex-wrap gap-2"
                  style={{ animationDelay: "360ms" }}
                >
                  <Button size="sm" variant="outline">
                    <IconPlus />
                    New Directive
                  </Button>
                  <Button size="sm" variant="outline">
                    <IconUserPlus />
                    Invite teammate
                  </Button>
                  <Button size="sm" variant="outline">
                    <IconPlugConnected />
                    Connect provider
                  </Button>
                  <Button size="sm" variant="outline">
                    <IconDownload />
                    Export
                  </Button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

export default function Page() {
  return (
    <DashboardShell>
      <OverviewWorkbench />
    </DashboardShell>
  )
}
