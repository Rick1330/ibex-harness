"use client"

import * as React from "react"
import { usePathname } from "next/navigation"
import { useTheme } from "@/components/theme-provider"
import {
  IconBell,
  IconChevronDown,
  IconDeviceDesktop,
  IconHelp,
  IconKey,
  IconLogout,
  IconMoon,
  IconSearch,
  IconSettings,
  IconSun,
  IconUser,
} from "@tabler/icons-react"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { TimeRangeControl } from "@/components/time-range-control"
import {
  FRESHNESS_TONE,
  SHELL_HEALTH,
  type FreshnessState,
} from "@/lib/shell-health"

const notifications = [
  {
    title: "Drift alert: latency p99 above baseline",
    detail: "trace_a91f · 2m ago",
  },
  {
    title: "Incident #42 moved to mitigated",
    detail: "session 88ac · 18m ago",
  },
  {
    title: "Evidence export finished",
    detail: "bundle_2026-02-11.zip · 1h ago",
  },
]

const pageMeta: Record<
  string,
  { section: string; page: string; search: string }
> = {
  "/dashboard": {
    section: "Overview",
    page: "Overview",
    search: "Search metrics, agents, sessions...",
  },
  "/dashboard/explore": {
    section: "Investigate",
    page: "Explore",
    search: "Jump to trace, request, session, agent...",
  },
}

function resolvePageMeta(pathname: string) {
  if (pathname.startsWith("/dashboard/explore/t/")) {
    return {
      section: "Investigate",
      page: "Trace Inspector",
      search: "Jump to span, memory, request...",
    }
  }
  if (
    pathname.startsWith("/dashboard/agents/") &&
    pathname !== "/dashboard/agents"
  ) {
    return {
      section: "Investigate",
      page: "Agent Detail",
      search: "Jump to sessions, directive...",
    }
  }
  if (pathname.startsWith("/dashboard/agents")) {
    return {
      section: "Investigate",
      page: "Agents",
      search: "Search agent name, directive...",
    }
  }
  if (
    pathname.startsWith("/dashboard/sessions/") &&
    pathname !== "/dashboard/sessions"
  ) {
    return {
      section: "Investigate",
      page: "Session Timeline",
      search: "Jump to turn, memory, checkpoint...",
    }
  }
  if (pathname.startsWith("/dashboard/sessions")) {
    return {
      section: "Investigate",
      page: "Sessions",
      search: "Search session_id, agent, tag...",
    }
  }
  if (
    pathname.startsWith("/dashboard/memories/") &&
    pathname !== "/dashboard/memories"
  ) {
    return {
      section: "Investigate",
      page: "Memory Detail",
      search: "Jump to lineage, session...",
    }
  }
  if (pathname.startsWith("/dashboard/memories")) {
    return {
      section: "Investigate",
      page: "Memories",
      search: "Search memory_id, category...",
    }
  }
  if (
    pathname.startsWith("/dashboard/directives/") &&
    pathname !== "/dashboard/directives"
  ) {
    return {
      section: "Govern",
      page: "Directive Detail",
      search: "Jump to version, scenario, ledger...",
    }
  }
  if (pathname.startsWith("/dashboard/directives")) {
    return {
      section: "Govern",
      page: "Directives",
      search: "Search directive name, agent...",
    }
  }
  if (
    pathname.startsWith("/dashboard/incidents/") &&
    pathname !== "/dashboard/incidents"
  ) {
    return {
      section: "Govern",
      page: "Incident Detail",
      search: "Jump to evidence, timeline...",
    }
  }
  if (pathname.startsWith("/dashboard/incidents")) {
    return {
      section: "Govern",
      page: "Incidents",
      search: "Search incident_id, dedupe_key, owner...",
    }
  }
  if (
    pathname.startsWith("/dashboard/drift/") &&
    pathname !== "/dashboard/drift"
  ) {
    return {
      section: "Govern",
      page: "Drift Alert",
      search: "Jump to evidence, fingerprint, traces...",
    }
  }
  if (pathname.startsWith("/dashboard/drift")) {
    return {
      section: "Govern",
      page: "Drift Alerts",
      search: "Search alert_id, agent, feature class...",
    }
  }
  if (pathname.startsWith("/dashboard/analytics")) {
    return {
      section: "Operate",
      page: "Analytics",
      search: "Jump to agent, trace, memory...",
    }
  }
  if (pathname.startsWith("/dashboard/billing")) {
    return {
      section: "Operate",
      page: "Billing",
      search: "Search rate card, request_id, agent...",
    }
  }
  if (pathname.startsWith("/dashboard/settings")) {
    return {
      section: "Operate",
      page: "Settings / Org",
      search: "Search member, token, provider...",
    }
  }
  if (pathname.startsWith("/dashboard/explore")) {
    return pageMeta["/dashboard/explore"]
  }
  return pageMeta[pathname] ?? pageMeta["/dashboard"]
}

function PageFreshness() {
  // Fixed initial value for SSR/client match; tick only after mount.
  const health = SHELL_HEALTH
  const [ago, setAgo] = React.useState(2)
  const [freshness, setFreshness] = React.useState<FreshnessState>(
    health.freshness,
  )
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
    const t = window.setInterval(() => {
      setAgo((s) => s + 5)
    }, 5000)
    return () => window.clearInterval(t)
  }, [])

  const tone = FRESHNESS_TONE[freshness]
  const lag = health.lag_ms != null ? ` · lag ${health.lag_ms}ms` : ""
  const conn =
    health.connection === "ready" ? "SSE drain ok" : `conn:${health.connection}`

  return (
    <button
      type="button"
      className="hidden items-center gap-1.5 rounded-full border border-sidebar-border px-2 py-1 text-[12px] whitespace-nowrap sm:flex"
      title={`${health.detail} · click to cycle freshness demo states`}
      onClick={() => {
        const order: FreshnessState[] = [
          "live",
          "historical",
          "reconnecting",
          "degraded",
          "partial",
          "stale",
        ]
        setFreshness(order[(order.indexOf(freshness) + 1) % order.length])
      }}
    >
      <span className="relative flex size-1.5 shrink-0">
        {freshness === "live" && (
          <span
            className={`absolute inline-flex h-full w-full animate-ping rounded-full ${tone.dot} opacity-75`}
          />
        )}
        <span
          className={`relative inline-flex size-1.5 rounded-full ${tone.dot}`}
        />
      </span>
      <span className="font-medium" suppressHydrationWarning>
        {tone.label} · synced {mounted ? ago : 2}s ago{lag}
      </span>
      <span className="hidden font-mono text-muted-foreground 2xl:inline">
        · {conn}
      </span>
    </button>
  )
}

function ThemeToggle() {
  const { theme, setTheme } = useTheme()
  const order = ["system", "light", "dark"] as const
  const current = (order as readonly string[]).includes(theme ?? "")
    ? (theme as (typeof order)[number])
    : "system"
  const next = order[(order.indexOf(current) + 1) % order.length]

  return (
    <Button
      variant="ghost"
      size="icon"
      className="size-8"
      onClick={() => setTheme(next)}
      title={`Theme: ${current} (click for ${next})`}
      aria-label={`Switch theme, current ${current}`}
    >
      {current === "light" ? (
        <IconSun className="size-4" />
      ) : current === "dark" ? (
        <IconMoon className="size-4" />
      ) : (
        <IconDeviceDesktop className="size-4" />
      )}
    </Button>
  )
}

export function SiteHeader() {
  const pathname = usePathname()
  const meta = resolvePageMeta(pathname)

  return (
    <header className="flex h-(--header-height) shrink-0 items-center gap-2 border-b transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-(--header-height)">
      <div className="flex w-full items-center gap-2 px-4 lg:px-6">
        {/* Left — Breadcrumb: Org → Section → Resource */}
        <div className="flex flex-1 items-center gap-2">
          <Breadcrumb className="hidden md:block">
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/dashboard">Acme Corp</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/dashboard">
                  {meta.section}
                </BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>{meta.page}</BreadcrumbPage>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
          {/* Compact/mobile: current page only */}
          <span className="text-sm font-medium md:hidden">{meta.page}</span>
        </div>

        {/* Center — Global search / Cmd+K trigger */}
        <button
          type="button"
          title="Search or jump to anything (Ctrl/⌘+K) — command palette not wired yet"
          className="hidden h-8 w-60 min-w-0 items-center gap-2 rounded-md border border-input bg-muted/50 px-2.5 text-sm text-muted-foreground transition-colors hover:bg-muted md:flex lg:w-72 xl:w-80"
        >
          <IconSearch className="size-4 shrink-0" />
          <span className="truncate">{meta.search}</span>
          <kbd className="ml-auto rounded border border-border bg-background px-1.5 font-mono text-[11px]">
            ⌘K
          </kbd>
        </button>
        <Button
          variant="ghost"
          size="icon"
          className="size-8 md:hidden"
          title="Search (Ctrl/⌘+K)"
          aria-label="Search"
        >
          <IconSearch className="size-4" />
        </Button>

        {/* Right */}
        <div className="flex flex-1 items-center justify-end gap-1">
          {/* Global time range + custom / as-of — only place these live */}
          <TimeRangeControl />

          {/* Page freshness chip */}
          <PageFreshness />

          {/* Notifications */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="relative size-8"
                title="Notifications"
                aria-label={`Notifications, ${notifications.length} unread`}
              >
                <IconBell className="size-4" />
                <span className="absolute top-0.5 right-0.5 flex size-4 items-center justify-center rounded-full bg-primary text-[11px] font-medium text-primary-foreground tabular-nums">
                  {notifications.length}
                </span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-80 rounded-xl">
              <DropdownMenuLabel>Notifications</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuGroup>
                {notifications.map((n) => (
                  <DropdownMenuItem
                    key={n.title}
                    className="flex-col items-start gap-0.5 py-2"
                  >
                    <span className="text-sm leading-snug font-medium whitespace-normal">
                      {n.title}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {n.detail}
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
            </DropdownMenuContent>
          </DropdownMenu>

          {/* Theme toggle */}
          <ThemeToggle />

          {/* Help / docs shortcut */}
          <Button
            variant="ghost"
            size="icon"
            asChild
            className="size-8"
            title="Help and docs"
          >
            <a href="https://ibexharness.com/docs" aria-label="Help and docs">
              <IconHelp className="size-4" />
            </a>
          </Button>

          {/* Account menu */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="h-8 gap-2 rounded-full px-1.5 sm:rounded-md sm:pr-2"
                title="Account"
                aria-label="Account menu"
              >
                <Avatar className="size-7 rounded-full ring-1 ring-border">
                  <AvatarImage src="/avatars/shadcn.jpg" alt="Operator" />
                  <AvatarFallback className="rounded-full text-[11px]">
                    OP
                  </AvatarFallback>
                </Avatar>
                <span className="hidden max-w-[9rem] truncate text-left text-[13px] font-medium sm:block">
                  Operator
                </span>
                <IconChevronDown className="hidden size-3.5 text-muted-foreground sm:block" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-72 rounded-xl p-1.5">
              <div className="flex items-center gap-3 rounded-lg bg-muted/50 px-2.5 py-2.5">
                <Avatar className="size-10 rounded-full ring-1 ring-border">
                  <AvatarImage src="/avatars/shadcn.jpg" alt="Operator" />
                  <AvatarFallback className="rounded-full text-[12px]">
                    OP
                  </AvatarFallback>
                </Avatar>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-[13px] font-medium">
                    Operator
                  </div>
                  <div className="truncate text-[12px] text-muted-foreground">
                    you@acme.com
                  </div>
                  <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                    Acme Corp · owner
                  </div>
                </div>
              </div>
              <DropdownMenuSeparator className="my-1.5" />
              <DropdownMenuGroup>
                <DropdownMenuItem asChild className="rounded-lg">
                  <a href="/dashboard/settings?tab=security">
                    <IconUser />
                    Profile & security
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="rounded-lg">
                  <a href="/dashboard/settings">
                    <IconSettings />
                    Organization
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="rounded-lg">
                  <a href="/dashboard/settings?tab=tokens">
                    <IconKey />
                    API tokens
                  </a>
                </DropdownMenuItem>
                <DropdownMenuItem asChild className="rounded-lg">
                  <a href="/dashboard/billing">
                    <IconSettings />
                    Billing & plan
                  </a>
                </DropdownMenuItem>
              </DropdownMenuGroup>
              <DropdownMenuSeparator className="my-1.5" />
              <DropdownMenuItem className="rounded-lg text-destructive focus:text-destructive">
                <IconLogout />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>
    </header>
  )
}
