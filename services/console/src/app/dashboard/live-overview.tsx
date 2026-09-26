import { cookies } from "next/headers"
import { IconAlertCircle, IconCheck, IconCircleX, IconMinus } from "@tabler/icons-react"
import type { ReactNode } from "react"

import { DashboardShell, pagePad, panelClass } from "@/components/sessions/dashboard-shell"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  fetchOperatorContext,
  fetchOperatorOverview,
  fetchOperatorPlatformHealth,
} from "@/lib/api/d1"
import type { OperatorContext, OperatorOverview, PlatformHealth } from "@/lib/api/contracts"
import { OperatorApiError } from "@/lib/api/transport"
import { OperatorSseStatus } from "./operator-sse-status"

const unavailableText = "Not connected in D1"
const formatObservedAt = (value: string) =>
  new Date(value).toISOString().replace("T", " ").replace("Z", " UTC")

function dependencyDotClass(status: string): string {
  if (status === "ok") return "bg-emerald-500"
  if (status === "degraded") return "bg-amber-500"
  return "bg-destructive"
}

function platformHealthPresentation(health: PlatformHealth | null): {
  icon: ReactNode
  label: string
} {
  if (!health) {
    return {
      icon: <IconCircleX className="size-4 text-destructive" aria-hidden />,
      label: "unavailable · platform health",
    }
  }
  const entries = Object.entries(health.dependency_health)
  const degraded = Boolean(health.degraded_mode || entries.some(([, status]) => status !== "ok"))
  if (degraded) {
    return {
      icon: <IconAlertCircle className="size-4 text-amber-600" aria-hidden />,
      label: "degraded · platform health",
    }
  }
  return {
    icon: <IconCheck className="size-4 text-emerald-600" aria-hidden />,
    label: "observed · platform health",
  }
}

function SystemsStrip({ health }: Readonly<{ health: PlatformHealth | null }>) {
  const entries = health ? Object.entries(health.dependency_health) : []
  const presentation = platformHealthPresentation(health)
  return (
    <Card className={panelClass}>
      <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-2 py-3">
        <output className="flex items-center gap-2 text-sm font-medium">
          {presentation.icon}
          {presentation.label}
        </output>
        {entries.map(([name, status]) => (
          <span key={name} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={`size-1.5 rounded-full ${dependencyDotClass(status)}`} />
            <span className="font-mono">{name}</span>
            <span>{status}</span>
          </span>
        ))}
        {!entries.length ? <span className="text-xs text-muted-foreground">{unavailableText}</span> : null}
        <OperatorSseStatus />
        <span className="ml-auto text-[12px] text-muted-foreground">
          {health ? `Observed ${formatObservedAt(health.observed_at)}` : "No stale or fixture health is shown"}
        </span>
      </CardContent>
    </Card>
  )
}

function AtAGlance({
  activeUsers,
  agents,
  activeAgents,
  observedAt,
}: Readonly<{
  activeUsers: number | null
  agents: number | null
  activeAgents: number | null
  observedAt: string | null
}>) {
  const metrics = [
    { label: "Agents", value: agents },
    { label: "Active agents", value: activeAgents },
    { label: "Requests", value: null },
    { label: "Sessions", value: null },
    { label: "Est. cost", value: null },
  ]
  return (
    <Card className={`${panelClass} rise`} style={{ animationDelay: "0ms" }}>
      <CardHeader className="gap-5">
        <div className="flex flex-wrap items-center gap-2">
          <CardDescription className="font-mono text-[12px] uppercase tracking-[0.18em]">At a glance</CardDescription>
          <span className="ml-auto rounded-full border px-2 py-0.5 font-mono text-[12px] text-muted-foreground">read-only · D1</span>
        </div>
        <div className="grid gap-3 md:grid-cols-[1fr_auto] md:items-end">
          <div>
            <CardDescription>Active users</CardDescription>
            <CardTitle className="mt-2 font-serif text-5xl font-normal tracking-normal tabular-nums md:text-7xl">
              {activeUsers === null ? "—" : activeUsers.toLocaleString("en-US")}
            </CardTitle>
          </div>
          <div className="text-sm text-muted-foreground">
            {observedAt ? `Observed ${formatObservedAt(observedAt)}` : "Organization count unavailable"}
          </div>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 border-t pt-5 sm:grid-cols-2 lg:grid-cols-5">
          {metrics.map(({ label, value }) => (
            <div key={label} className="min-w-0">
              <div className="text-xs text-muted-foreground">{label}</div>
              <div className="mt-1 font-mono text-xl font-medium tabular-nums">
                {value === null ? "—" : value.toLocaleString("en-US")}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                {value === null ? unavailableText : "Authoritative organization snapshot"}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function UnconnectedPanel({
  title,
  description,
}: Readonly<{
  title: string
  description: string
}>) {
  return (
    <Card className={`${panelClass} rise`}>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-2 text-sm text-muted-foreground">
        <IconMinus className="size-4" aria-hidden />
        {unavailableText}. No mock data is substituted.
      </CardContent>
    </Card>
  )
}

type OverviewLoad = {
  context: OperatorContext | null
  overview: OperatorOverview | null
  health: PlatformHealth | null
  authUnavailable: boolean
  overviewError: unknown
}

async function loadOverviewSnapshot(): Promise<OverviewLoad> {
  const cookieStore = await cookies()
  const sessionName = process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME || "ibex_session"
  const value = cookieStore.get(sessionName)?.value
  const cookieHeader = value ? `${sessionName}=${value}` : undefined
  const [contextResult, overviewResult, healthResult] = await Promise.allSettled([
    fetchOperatorContext(cookieHeader),
    fetchOperatorOverview(cookieHeader),
    fetchOperatorPlatformHealth(cookieHeader),
  ])
  const context = contextResult.status === "fulfilled" ? contextResult.value : null
  const overview = overviewResult.status === "fulfilled" ? overviewResult.value : null
  const health = healthResult.status === "fulfilled" ? healthResult.value : null
  const contextError = contextResult.status === "rejected" ? contextResult.reason : null
  const overviewError = overviewResult.status === "rejected" ? overviewResult.reason : null
  const authUnavailable =
    contextError instanceof OperatorApiError && [401, 403].includes(contextError.status)
  return { context, overview, health, authUnavailable, overviewError }
}

function OverviewStatusBanners({
  authUnavailable,
  overview,
  overviewError,
}: Readonly<{
  authUnavailable: boolean
  overview: OperatorOverview | null
  overviewError: unknown
}>) {
  if (authUnavailable) {
    return (
      <output className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm">
        Operator session is missing, expired, or lacks metadata-read permission. No preview data is shown.
      </output>
    )
  }
  if (overview) return null
  const requestId =
    overviewError instanceof OperatorApiError && overviewError.requestId
      ? overviewError.requestId
      : null
  return (
    <output className="rounded-md border border-destructive/40 bg-destructive/5 px-3 py-2 text-sm">
      Organization overview is unavailable. No mock values are substituted.
      {requestId ? <span className="ml-2 font-mono text-xs">Reference: {requestId}</span> : null}
    </output>
  )
}

export async function LiveOverview() {
  const { context, overview, health, authUnavailable, overviewError } = await loadOverviewSnapshot()
  const rolePrefix = context?.role ? `${context.role} · ` : ""
  const subtitle = context ? context.org_slug : "Verified organization context is unavailable."

  return (
    <DashboardShell
      liveMode
      showPreviewBanner={false}
      operatorContext={context}
      platformHealth={health}
    >
      <main className="@container/main flex flex-1 flex-col gap-2">
        <div className={`${pagePad} md:gap-4`}>
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="font-mono text-[12px] uppercase tracking-[0.18em] text-muted-foreground">Overview</p>
              <h1 className="mt-2 font-serif text-4xl font-normal tracking-normal md:text-5xl">
                {overview?.org_name ?? "Organization overview"}
              </h1>
              <p className="mt-2 text-sm text-muted-foreground">
                {rolePrefix}
                {subtitle}
              </p>
            </div>
          </div>
          <OverviewStatusBanners
            authUnavailable={authUnavailable}
            overview={overview}
            overviewError={overviewError}
          />
          <SystemsStrip health={health} />
          <AtAGlance
            activeUsers={overview?.counts.active_users ?? null}
            agents={overview?.counts.agents ?? null}
            activeAgents={overview?.counts.active_agents ?? null}
            observedAt={overview?.observed_at ?? null}
          />
          <UnconnectedPanel
            title="Request volume & errors"
            description="Fingerprint-style scalar trends — expected band as reference, anomaly marked on the current hour."
          />
          <div className="grid gap-4 lg:grid-cols-2">
            <UnconnectedPanel title="Latency breakdown" description="p50 / p95 / p99 per stage" />
            <UnconnectedPanel title="Top agents" description="By request count in period" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <UnconnectedPanel title="Model distribution" description="Share of requests by model" />
            <UnconnectedPanel title="Recent activity" description="Operational changes in this workspace" />
          </div>
          <p className="border-t pt-3 text-xs text-muted-foreground">
            D1 is read-only. Organization counts are complete at their observation time; activity, analytics, cost, and mutations remain unavailable until their later Phase 4 milestones.
          </p>
        </div>
      </main>
    </DashboardShell>
  )
}
