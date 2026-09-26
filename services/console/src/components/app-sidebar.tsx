"use client"

import * as React from "react"
import Image from "next/image"
import { usePathname, useRouter } from "next/navigation"
import {
  IconAlertTriangle,
  IconBrain,
  IconChartBar,
  IconCheck,
  IconChevronDown,
  IconChevronRight,
  IconChevronsLeft,
  IconChevronsRight,
  IconCompass,
  IconCreditCard,
  IconDashboard,
  IconFileDescription,
  IconGlobe,
  IconHistory,
  IconLock,
  IconMessages,
  IconRadar2,
  IconRobot,
  IconRoute,
  IconSettings,
  IconStar,
  IconListCheck,
  type Icon,
} from "@tabler/icons-react"

import { useOnboardingOptional } from "@/components/onboarding/onboarding-provider"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { OPEN_DRIFT_COUNT } from "@/lib/drift/fixtures"
import type { OperatorContext } from "@/lib/api/contracts"

const orgs = [
  { name: "Acme Corp", plan: "Pro", color: "bg-foreground" },
  { name: "Globex", plan: "self-hosted", color: "bg-muted-foreground" },
]
const envs = ["Production", "Staging"]

type IbexNavItem = {
  title: string
  url: string
  icon: Icon
  badge?: string
  badgeTitle?: string
  /** Reason text for the lock flag. Shown as tooltip + screen-reader text. */
  lock?: string
  isActive?: boolean
}

const navGroups: { label: string; items: IbexNavItem[] }[] = [
  {
    label: "Overview",
    items: [
      { title: "Overview", url: "/dashboard", icon: IconDashboard },
      {
        title: "Explore",
        url: "/dashboard/explore",
        icon: IconCompass,
        badge: "all",
        badgeTitle: "Global trace scope — no agent selection required",
      },
    ],
  },
  {
    label: "Investigate",
    items: [
      { title: "Agents", url: "/dashboard/agents", icon: IconRobot },
      { title: "Sessions", url: "/dashboard/sessions", icon: IconMessages },
      { title: "Traces", url: "/dashboard/explore", icon: IconRoute },
      { title: "Memories", url: "/dashboard/memories", icon: IconBrain },
    ],
  },
  {
    label: "Govern",
    items: [
      {
        title: "Directives",
        url: "/dashboard/directives",
        icon: IconFileDescription,
      },
      {
        title: "Incidents",
        url: "/dashboard/incidents",
        icon: IconAlertTriangle,
        badge: "2",
        badgeTitle: "2 open / acknowledged SEV1–2 incidents",
      },
      {
        title: "Drift Alerts",
        url: "/dashboard/drift",
        icon: IconRadar2,
        badge: String(OPEN_DRIFT_COUNT),
        badgeTitle: `${OPEN_DRIFT_COUNT} open drift alerts (idx_drift_alerts_open)`,
      },
    ],
  },
  {
    label: "Operate",
    items: [
      { title: "Analytics", url: "/dashboard/analytics", icon: IconChartBar },
      {
        title: "Billing",
        url: "/dashboard/billing",
        icon: IconCreditCard,
        badge: "est.",
        badgeTitle:
          "Estimated spend vs cap — actuals pending reconciliation (#859)",
      },
      {
        title: "Settings / Org",
        url: "/dashboard/settings",
        icon: IconSettings,
      },
    ],
  },
]

const pinned: IbexNavItem[] = [
  {
    title: "Trace #a91f (prod outage)",
    url: "/dashboard/explore/t/trace_a91f7c",
    icon: IconRoute,
  },
  {
    title: "Δrank / budget (b02e)",
    url: "/dashboard/explore/t/trace_b02e44",
    icon: IconRoute,
  },
  {
    title: "Directive support-refund",
    url: "/dashboard/directives/dir_support_refund",
    icon: IconFileDescription,
  },
]

const recent: IbexNavItem[] = [
  {
    title: "Session abc123…",
    url: "/dashboard/sessions/sess_client_abc123",
    icon: IconMessages,
  },
  {
    title: "Memory a1b2c3d4",
    url: "/dashboard/memories/mem_a1b2c3d4",
    icon: IconBrain,
  },
]

function OrgEnvSwitcher({
  liveMode,
  operatorContext,
}: Readonly<{
  liveMode: boolean
  operatorContext: OperatorContext | null
}>) {
  return liveMode ? (
    <LiveOrgSwitcher operatorContext={operatorContext} />
  ) : (
    <PreviewOrgEnvSwitcher />
  )
}

function LiveOrgSwitcher({
  operatorContext,
}: Readonly<{ operatorContext: OperatorContext | null }>) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton
            size="lg"
            disabled
            tooltip="Tenant scope comes from the verified operator session; switching is not available in D1."
            className="border border-sidebar-border bg-sidebar-accent/40"
          >
            <span aria-hidden className="size-2.5 shrink-0 rounded-full bg-foreground" />
            <span className="grid flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
              <span className="truncate text-sm font-medium">{operatorContext?.org_name ?? "Organization"}</span>
              <span className="truncate text-xs text-muted-foreground">
                {operatorContext ? `${operatorContext.org_slug} · read-only` : "Context unavailable · read-only"}
              </span>
            </span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
}

function PreviewOrgEnvSwitcher() {
  const [org, setOrg] = React.useState(orgs[0])
  const [env, setEnv] = React.useState(envs[0])

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              tooltip={`${org.name} · ${org.plan} · ${env} (server-derived org context)`}
              className="border border-sidebar-border bg-sidebar-accent/40 hover:bg-sidebar-accent focus-visible:ring-2"
            >
              <span
                aria-hidden
                className={`size-2.5 shrink-0 rounded-full ${org.color}`}
              />
              <span className="grid flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
                <span className="truncate text-sm font-medium">
                  {org.name}{" "}
                  <span className="font-normal text-muted-foreground">
                    · {org.plan}
                  </span>
                </span>
                <span className="flex items-center gap-1 truncate text-xs text-muted-foreground">
                  <IconGlobe className="size-3 shrink-0" />
                  {env}
                  <IconChevronRight className="size-3 shrink-0" />
                </span>
              </span>
              <IconChevronDown className="ml-auto size-4 shrink-0 group-data-[collapsible=icon]:hidden" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            align="start"
            side="right"
            className="w-56 rounded-lg"
          >
            <DropdownMenuLabel>Organization</DropdownMenuLabel>
            {orgs.map((o) => (
              <DropdownMenuItem key={o.name} onSelect={() => setOrg(o)}>
                {org.name === o.name ? (
                  <IconCheck className="size-4" />
                ) : (
                  <span
                    aria-hidden
                    className={`size-2 rounded-full ${o.color} ml-1`}
                  />
                )}
                <span className={org.name === o.name ? "" : "pl-2"}>
                  {o.name}{" "}
                  <span className="text-muted-foreground">· {o.plan}</span>
                </span>
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Environment</DropdownMenuLabel>
            {envs.map((name) => (
              <DropdownMenuItem key={name} onSelect={() => setEnv(name)}>
                {env === name && <IconCheck className="size-4" />}
                <span className={env === name ? "" : "pl-6"}>{name}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

function NavGroup({ label, items }: { label: string; items: IbexNavItem[] }) {
  const pathname = usePathname()

  return (
    <SidebarGroup>
      <SidebarGroupLabel className="group-data-[collapsible=icon]:hidden">
        {label}
      </SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => (
            <SidebarMenuItem key={item.title}>
              <SidebarMenuButton
                asChild
                tooltip={item.lock ?? item.badgeTitle ?? item.title}
                isActive={
                  item.url === "/dashboard"
                    ? pathname === item.url
                    : pathname.startsWith(item.url)
                }
              >
                <a href={item.url}>
                  <item.icon className="group-data-[collapsible=icon]:size-5!" />
                  <span className="group-data-[collapsible=icon]:hidden">
                    {item.title}
                  </span>
                  {item.lock && (
                    <>
                      <IconLock
                        className="ml-auto size-3.5 shrink-0 text-amber-600 group-data-[collapsible=icon]:hidden dark:text-amber-400"
                        aria-hidden
                      />
                      <span className="sr-only">{item.lock}</span>
                    </>
                  )}
                </a>
              </SidebarMenuButton>
              {item.badge && !item.lock && (
                <SidebarMenuBadge title={item.badgeTitle}>
                  {item.badge}
                </SidebarMenuBadge>
              )}
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  )
}

function CollapseToggle() {
  const { state, toggleSidebar } = useSidebar()
  const collapsed = state === "collapsed"

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          onClick={toggleSidebar}
          tooltip={collapsed ? "Expand sidebar" : "Collapse to icons"}
        >
          {collapsed ? (
            <IconChevronsRight className="group-data-[collapsible=icon]:size-5!" />
          ) : (
            <IconChevronsLeft className="group-data-[collapsible=icon]:size-5!" />
          )}
          <span className="group-data-[collapsible=icon]:hidden">
            {collapsed ? "Expand" : "Collapse"}
          </span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

function SetupGuideLink() {
  const onboarding = useOnboardingOptional()
  const router = useRouter()
  if (!onboarding?.showSetupGuide) return null

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <SidebarMenuButton
          tooltip="Setup guide"
          onClick={() => {
            onboarding.openChecklist()
            router.push("/dashboard#onboarding")
          }}
        >
          <IconListCheck className="group-data-[collapsible=icon]:size-5!" />
          <span className="group-data-[collapsible=icon]:hidden">
            Setup guide
          </span>
        </SidebarMenuButton>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

type AppSidebarProps = Readonly<
  React.ComponentProps<typeof Sidebar> & {
    liveMode?: boolean
    operatorContext?: OperatorContext | null
  }
>

export function AppSidebar({
  liveMode = false,
  operatorContext = null,
  ...props
}: AppSidebarProps) {
  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader className="gap-2">
        {/* Row 1 — Brand: static identity, non-interactive */}
        <div className="flex items-center gap-2 px-1.5 py-1">
          <Image
            src="/brand/ibex-mark-light.png"
            alt="IBEX Harness"
            width={32}
            height={32}
            className="size-8 shrink-0 rounded-lg dark:hidden"
          />
          <Image
            src="/brand/ibex-mark-dark.png"
            alt=""
            aria-hidden
            width={32}
            height={32}
            className="hidden size-8 shrink-0 rounded-lg dark:block"
          />
          <span className="text-base font-semibold tracking-wide group-data-[collapsible=icon]:hidden">
            IBEX HARNESS
          </span>
        </div>
        <div aria-hidden className="mx-1 border-t border-sidebar-border" />
        {/* Row 2 — Org switcher: functional control, own card treatment */}
        <OrgEnvSwitcher liveMode={liveMode} operatorContext={operatorContext} />
      </SidebarHeader>
      <SidebarContent>
        {navGroups.map((group) => (
            <NavGroup
              key={group.label}
              label={group.label}
              items={
                liveMode
                ? group.items.map((item) => {
                    const liveItem = { ...item }
                    delete liveItem.badge
                    delete liveItem.badgeTitle
                    return liveItem
                  })
                : group.items
              }
          />
        ))}
        {!liveMode ? <SidebarGroup>
          <SidebarGroupLabel className="group-data-[collapsible=icon]:hidden">
            <IconStar className="mr-1 size-3" />
            Pinned
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {pinned.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild tooltip={item.title}>
                    <a href={item.url}>
                      <item.icon className="group-data-[collapsible=icon]:size-5!" />
                      <span className="group-data-[collapsible=icon]:hidden">
                        {item.title}
                      </span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup> : null}
        {!liveMode ? <SidebarGroup>
          <SidebarGroupLabel className="group-data-[collapsible=icon]:hidden">
            <IconHistory className="mr-1 size-3" />
            Recent
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {recent.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild tooltip={item.title}>
                    <a href={item.url}>
                      <item.icon className="group-data-[collapsible=icon]:size-5!" />
                      <span className="group-data-[collapsible=icon]:hidden">
                        {item.title}
                      </span>
                    </a>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup> : null}
      </SidebarContent>
      <SidebarFooter>
        {!liveMode ? <SetupGuideLink /> : null}
        <CollapseToggle />
      </SidebarFooter>
    </Sidebar>
  )
}
