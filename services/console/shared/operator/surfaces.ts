export type SurfaceAvailability = "live" | "preview"
export type RuntimeAvailability = "live" | "partial" | "unavailable"
export type SurfacePhase = "A" | "B1" | "B2"

/**
 * Core surfaces are the memory/context lifecycle and form the default Console.
 * Platform surfaces are designed previews that stay out of the default
 * navigation until a named design partner and an owning contract exist.
 * See ADR-0089.
 */
export type SurfaceTier = "core" | "platform"

export type SurfaceDefinition = {
  path: string
  label: string
  tier: SurfaceTier
  availability: SurfaceAvailability
  domain: "D1" | "D2" | "D3" | "D4" | "D5" | "D6"
  phase: SurfacePhase
  group: string
  question: string
  description: string
  contract: string
}

/**
 * Static product surface status. Runtime state (live/partial/unavailable) is
 * layered on top from the BFF; preview surfaces never become live merely
 * because an upstream endpoint exists.
 */
export const SURFACES = {
  overview: {
    path: "/",
    label: "Overview",
    tier: "core",
    availability: "live",
    domain: "D1",
    phase: "A",
    group: "Lifecycle",
    question: "What is the organization's memory and context doing right now?",
    description: "Tenant-scoped organization snapshot and platform health.",
    contract: "operator.overview.v1 + operator.platform.health.v1",
  },
  agents: {
    path: "/agents",
    label: "Agents",
    tier: "core",
    availability: "live",
    domain: "D2",
    phase: "B2",
    group: "Lifecycle",
    question: "Which agents write and read memory, and how are they behaving?",
    description: "Tenant-scoped agent inventory with status, provider, usage counters, and last activity.",
    contract: "operator.agents.v1",
  },
  sessions: {
    path: "/sessions",
    label: "Sessions",
    tier: "core",
    availability: "live",
    domain: "D3",
    phase: "B1",
    group: "Lifecycle",
    question: "What happened across this agent session, turn by turn?",
    description: "Tenant-scoped session index with turn counts, status, token totals, latency, and the turn-to-trace ledger.",
    contract: "operator.sessions.v1",
  },
  memories: {
    path: "/memories",
    label: "Memories",
    tier: "core",
    availability: "live",
    domain: "D2",
    phase: "B1",
    group: "Lifecycle",
    question: "What did the agent store and retrieve?",
    description: "Tenant-scoped memory index with classification, lifecycle, provenance, usage counters, and validity.",
    contract: "operator.memories.v1",
  },
  evidence: {
    path: "/evidence",
    label: "Evidence",
    tier: "core",
    availability: "live",
    domain: "D2",
    phase: "B2",
    group: "Lifecycle",
    question: "Which runs hold a complete capture, which do not, and did the delivery chain settle?",
    description: "Capture completeness and relay delivery from operator.evidence.summary.v1, deletion evidence and audit continuity from operator.evidence.deletions.v1; field-level redaction needs its own contract.",
    contract: "operator.evidence.summary.v1",
  },
  directives: {
    path: "/directives",
    label: "Directives",
    tier: "core",
    availability: "live",
    domain: "D5",
    phase: "B2",
    group: "Context",
    question: "Which instruction version a new session resolves to, and which versions exist?",
    description: "Version timeline and per-version usage from operator.directives.versions.v1; instruction text and diffs need their own contract.",
    contract: "operator.directives.versions.v1",
  },
  policies: {
    path: "/policies",
    label: "Policies",
    tier: "core",
    availability: "preview",
    domain: "D4",
    phase: "B1",
    group: "Context",
    question: "Which rules were in force when this ran?",
    description: "Policy snapshots, readable rules, and diffs are planned.",
    contract: "operator.policies.snapshots.v1",
  },
  explore: {
    path: "/explore",
    label: "Explore",
    tier: "core",
    availability: "live",
    domain: "D2",
    phase: "A",
    group: "Investigate",
    question: "Why did this run behave the way it did?",
    description: "Read-only trace metadata across the current organization.",
    contract: "operator.trace-list.v1 / operator.trace-detail.v1",
  },
  platform: {
    path: "/platform",
    label: "Platform",
    tier: "core",
    availability: "live",
    domain: "D1",
    phase: "A",
    group: "Operate",
    question: "Are dependencies, ingestion and recovery healthy?",
    description: "Dependency health, ingestion lag, retention, recovery, and deploy evidence.",
    contract: "operator.platform.health.v1",
  },
  settings: {
    path: "/settings",
    label: "Settings",
    tier: "core",
    availability: "preview",
    domain: "D1",
    phase: "B2",
    group: "Operate",
    question: "How is this organization configured?",
    description: "Organization, environments, retention, display, and notifications are planned.",
    contract: "operator.settings.v1 [NEEDS-BACKEND]",
  },
  incidents: {
    path: "/incidents",
    label: "Incidents",
    tier: "platform",
    availability: "preview",
    domain: "D4",
    phase: "B2",
    group: "Platform",
    question: "What is broken now, and who owns it?",
    description: "Incident response and acknowledgement are planned.",
    contract: "operator.incidents.list.v1 [NEEDS-BACKEND]",
  },
  drift: {
    path: "/drift",
    label: "Drift",
    tier: "platform",
    availability: "preview",
    domain: "D4",
    phase: "B2",
    group: "Platform",
    question: "Has behaviour moved away from its baseline?",
    description: "Drift alerts and fingerprint history are planned.",
    contract: "operator.drift.alerts.v1 [NEEDS-BACKEND]",
  },
  "audit": {
    path: "/audit",
    label: "Audit log",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B2",
    group: "Platform",
    question: "Who changed what, and was it applied once?",
    description: "Audit events, idempotency keys, and diffs are planned.",
    contract: "operator.audit.list.v1 [NEEDS-BACKEND]",
  },
  budgets: {
    path: "/budgets",
    label: "Budgets",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B1",
    group: "Platform",
    question: "Which reservations are close to their limit?",
    description: "Budget reservations and headroom are planned.",
    contract: "operator.budgets.reservations.v1",
  },
  analytics: {
    path: "/analytics",
    label: "Analytics",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B2",
    group: "Platform",
    question: "Where do spend, tokens and latency go over time?",
    description: "Cost and usage analytics are planned.",
    contract: "operator.analytics.usage.v1 [NEEDS-BACKEND]",
  },
  providers: {
    path: "/providers",
    label: "Providers",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B1",
    group: "Platform",
    question: "Which providers and models are configured, and with what limits?",
    description: "Provider manifests and model capabilities are planned.",
    contract: "operator.providers.manifest.v1",
  },
  "mcp-tools": {
    path: "/mcp-tools",
    label: "MCP tools",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B1",
    group: "Platform",
    question: "Which operator tools exist, and who may call them?",
    description: "Operator tool inventory and schemas are planned.",
    contract: "operator.mcp.tools.v1",
  },
  access: {
    path: "/access",
    label: "Access",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B2",
    group: "Platform",
    question: "Which keys and members can do what?",
    description: "Keys, scopes, and the members and roles matrix are planned.",
    contract: "operator.access.keys.v1 + members.v1 [NEEDS-BACKEND]",
  },
} as const satisfies Record<string, SurfaceDefinition>

export type SurfaceKey = keyof typeof SURFACES

export const SURFACE_LIST: SurfaceDefinition[] = Object.values(SURFACES)

export const CORE_SURFACES: SurfaceDefinition[] = SURFACE_LIST.filter((surface) => surface.tier === "core")

export const PLATFORM_SURFACES: SurfaceDefinition[] = SURFACE_LIST.filter((surface) => surface.tier === "platform")

export const CORE_GROUPS = ["Lifecycle", "Context", "Investigate", "Operate"] as const

export function availabilityLabel(availability: SurfaceAvailability): string {
  return availability === "live" ? "Live surface" : "Preview"
}

export function runtimeLabel(runtime: RuntimeAvailability): string {
  if (runtime === "live") return "Live"
  if (runtime === "partial") return "Partial data"
  return "Unavailable"
}

export function tierLabel(tier: SurfaceTier): string {
  return tier === "core" ? "Core surface" : "Platform tier"
}

export function surfaceForPath(path: string): SurfaceDefinition | null {
  if (path === "/") return SURFACES.overview
  const key = path.split("/").find(Boolean)
  if (!key) return SURFACES.overview
  if (key === "explore") return SURFACES.explore
  return (SURFACES as Record<string, SurfaceDefinition>)[key] ?? null
}
