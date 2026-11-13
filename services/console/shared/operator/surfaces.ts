export type SurfaceAvailability = "live" | "preview"
export type RuntimeAvailability = "live" | "partial" | "unavailable"
export type SurfacePhase = "A" | "B1" | "B2"

/**
 * "registry" means `contract` names one or more contract IDs that exist in
 * `engineering/architecture-v2/contracts/rest-route-registry.json`. "design"
 * means the surface has no served route yet, so `contract` is absent rather
 * than invented. See ADR-0089.
 */
export type SurfaceContractStatus = "registry" | "design"

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
  /**
   * The registry contract(s) this surface reads, joined with " + ". Every ID here
   * must appear in `engineering/architecture-v2/contracts/rest-route-registry.json`
   * (REST `routes`, `grpc_methods`, or `mcp_tools`); `tests/surfaces.test.ts` fails
   * when one does not. Absent on a design-only surface: naming a contract the
   * registry does not carry would be a claim nothing backs.
   */
  contract?: string
  contractStatus: SurfaceContractStatus
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
    contract: "operator.overview.read.v1 + operator.platform.health.v1",
    contractStatus: "registry",
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
    description:
      "Tenant-scoped agent inventory with status, provider, usage counters, and last activity.",
    contract: "operator.agents.read.v1",
    contractStatus: "registry",
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
    description:
      "Tenant-scoped session index with turn counts, status, token totals, latency, and the turn-to-trace ledger.",
    contract: "operator.sessions.read.v1",
    contractStatus: "registry",
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
    description:
      "Tenant-scoped memory index with classification, lifecycle, provenance, usage counters, and validity.",
    contract: "operator.memories.read.v1",
    contractStatus: "registry",
  },
  evidence: {
    path: "/evidence",
    label: "Evidence",
    tier: "core",
    availability: "live",
    domain: "D2",
    phase: "B2",
    group: "Lifecycle",
    question:
      "Which runs hold a complete capture, which do not, and did the delivery chain settle?",
    description:
      "Capture completeness and relay delivery from operator.evidence.summary.v1, deletion evidence and audit continuity from operator.evidence.deletions.v1; field-level redaction needs its own contract.",
    contract: "operator.evidence.summary.v1",
    contractStatus: "registry",
  },
  directives: {
    path: "/directives",
    label: "Directives",
    tier: "core",
    availability: "live",
    domain: "D5",
    phase: "B2",
    group: "Context",
    question:
      "Which instruction version a new session resolves to, and which versions exist?",
    description:
      "Version timeline and per-version usage from operator.directives.read.v1 and operator.directives.get.v1; instruction text and diffs need their own contract.",
    contract: "operator.directives.read.v1 + operator.directives.get.v1",
    contractStatus: "registry",
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
    // Design-only: no operator policy route is served, so there is no registry
    // contract to name. The preview renders labelled illustrative fixtures.
    contractStatus: "design",
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
    contract: "operator.traces.read.v1 + operator.traces.get.v1",
    contractStatus: "registry",
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
    description:
      "Dependency health, ingestion lag, retention, recovery, and deploy evidence.",
    contract: "operator.platform.health.v1",
    contractStatus: "registry",
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
    description:
      "Organization, environments, retention, display, and notifications are planned.",
    // Design-only: organization settings have no served route yet.
    contractStatus: "design",
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
    // Design-only: incident response has no served route yet.
    contractStatus: "design",
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
    // Design-only: drift alerts have no served route yet.
    contractStatus: "design",
  },
  audit: {
    path: "/audit",
    label: "Audit log",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B2",
    group: "Platform",
    question: "Who changed what, and was it applied once?",
    description: "Audit events, idempotency keys, and diffs are planned.",
    // Design-only: the audit log has no served route yet.
    contractStatus: "design",
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
    // Design-only: budget reservations have no served operator route yet.
    contractStatus: "design",
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
    // Design-only: usage analytics have no served route yet.
    contractStatus: "design",
  },
  providers: {
    path: "/providers",
    label: "Providers",
    tier: "platform",
    availability: "preview",
    domain: "D6",
    phase: "B1",
    group: "Platform",
    question:
      "Which providers and models are configured, and with what limits?",
    description: "Provider manifests and model capabilities are planned.",
    // Design-only: provider manifests have no served operator route yet.
    contractStatus: "design",
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
    // Design-only: the operator tool inventory has no served route yet.
    contractStatus: "design",
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
    // Design-only: keys, scopes, and the members matrix have no served route yet.
    contractStatus: "design",
  },
} as const satisfies Record<string, SurfaceDefinition>

export type SurfaceKey = keyof typeof SURFACES

export const SURFACE_LIST: SurfaceDefinition[] = Object.values(SURFACES)

export const CORE_SURFACES: SurfaceDefinition[] = SURFACE_LIST.filter(
  (surface) => surface.tier === "core",
)

export const PLATFORM_SURFACES: SurfaceDefinition[] = SURFACE_LIST.filter(
  (surface) => surface.tier === "platform",
)

export const CORE_GROUPS = [
  "Lifecycle",
  "Context",
  "Investigate",
  "Operate",
] as const

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
