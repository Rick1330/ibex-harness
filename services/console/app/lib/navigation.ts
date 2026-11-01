import type { Component } from "vue"
import {
  Activity,
  BadgeCheck,
  Bot,
  ChartColumn,
  Compass,
  Database,
  History,
  KeyRound,
  LayoutGrid,
  MessagesSquare,
  Plug,
  ScrollText,
  Server,
  Settings,
  ShieldCheck,
  TriangleAlert,
  Wallet,
  Wrench,
} from "@lucide/vue"
import {
  CORE_GROUPS,
  SURFACES,
  type SurfaceDefinition,
  type SurfaceKey,
  type SurfaceTier,
} from "~~/shared/operator/surfaces"

export type NavAvailability = "live" | "preview"
export type NavPhase = "A" | "B1" | "B2"

export type NavItem = {
  key: SurfaceKey
  label: string
  to: string
  icon: Component
  tier: SurfaceTier
  group: string
  availability: NavAvailability
  phase: NavPhase
  question: string
  description: string
}

export type NavGroup = {
  label: string
  items: NavItem[]
}

export type AreaRailLink = {
  label: string
  to: string
  hint?: string
  preview?: boolean
}

export type AreaRail = {
  label: string
  note: string
  links: AreaRailLink[]
}

const icons: Record<SurfaceKey, Component> = {
  overview: LayoutGrid,
  agents: Bot,
  sessions: MessagesSquare,
  memories: Database,
  evidence: BadgeCheck,
  directives: ScrollText,
  policies: ShieldCheck,
  explore: Compass,
  platform: Server,
  settings: Settings,
  incidents: TriangleAlert,
  drift: Activity,
  audit: History,
  budgets: Wallet,
  analytics: ChartColumn,
  providers: Plug,
  "mcp-tools": Wrench,
  access: KeyRound,
}

/**
 * Presentation order inside a navigation group. Surface status and grouping
 * come from `SURFACES`; only the order is a navigation concern.
 */
const coreOrder: SurfaceKey[] = [
  "overview",
  "agents",
  "sessions",
  "memories",
  "evidence",
  "directives",
  "policies",
  "explore",
  "platform",
  "settings",
]

function toNavItem(key: SurfaceKey, surface: SurfaceDefinition): NavItem {
  return {
    key,
    label: surface.label,
    to: surface.path,
    icon: icons[key],
    tier: surface.tier,
    group: surface.group,
    availability: surface.availability,
    phase: surface.phase,
    question: surface.question,
    description: surface.description,
  }
}

const navByKey = new Map<SurfaceKey, NavItem>(
  (Object.entries(SURFACES) as [SurfaceKey, SurfaceDefinition][]).map(([key, surface]) => [
    key,
    toNavItem(key, surface),
  ]),
)

function orderedCore(key: SurfaceKey): NavItem {
  const item = navByKey.get(key)
  if (!item) throw new Error(`Unknown core surface: ${key}`)
  return item
}

export const primaryNavigation: NavGroup[] = CORE_GROUPS.map((label) => ({
  label,
  items: coreOrder.filter((key) => navByKey.get(key)?.group === label).map(orderedCore),
}))

export const platformNavigation: NavItem[] = (
  Object.entries(SURFACES) as [SurfaceKey, SurfaceDefinition][]
)
  .filter(([, surface]) => surface.tier === "platform")
  .map(([key, surface]) => toNavItem(key, surface))

export const footerNavigation = [
  {
    label: "Documentation",
    href: "https://ibexharness.com/docs",
  },
  {
    label: "Status and evidence",
    href: "https://ibexharness.com/docs/architecture/status-and-evidence",
  },
] as const

export const areaRails: Record<string, AreaRail> = {
  "/explore": {
    label: "Explore area",
    note: "Saved views live in the URL and can be copied like any other console link.",
    links: [
      { label: "All runs", to: "/explore", hint: "No status filter" },
      { label: "Errors", to: "/explore?status=error", hint: "Reported errors" },
      { label: "Healthy", to: "/explore?status=ok", hint: "Reported ok" },
      { label: "Latest 25", to: "/explore?limit=25", hint: "Smaller page" },
    ],
  },
  "/sessions": {
    label: "Session lenses",
    note: "Preview only. No session read model is connected.",
    links: [
      { label: "Timeline", to: "/sessions#timeline", preview: true },
      { label: "Trajectory", to: "/sessions#trajectory", preview: true },
      { label: "Inspector", to: "/sessions#inspector", preview: true },
    ],
  },
}

export const allNavigationItems: NavItem[] = [...primaryNavigation.flatMap((group) => group.items), ...platformNavigation]

export function findNavigationItem(path: string): NavItem | null {
  return (
    allNavigationItems
      .filter((item) => (item.to === "/" ? path === "/" : path === item.to || path.startsWith(`${item.to}/`)))
      .sort((left, right) => right.to.length - left.to.length)[0] ?? null
  )
}

export function navigationGroupFor(item: NavItem): string {
  return item.group
}
