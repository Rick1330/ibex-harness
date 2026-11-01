/**
 * Illustrative incident fixtures for the Monitor › Incidents surface.
 *
 * There is no incident read model in the operator contract yet, so every record
 * here is a design fixture. The page says so in its header and in the About
 * popover; no count on this page is presented as a live organization fact.
 *
 * The fixed clock in `govern-format` keeps relative ages stable between the
 * server render and the client hydration.
 */

export type IncidentSeverity = "SEV-1" | "SEV-2" | "SEV-3" | "SEV-4"
export type IncidentState = "investigating" | "identified" | "mitigating" | "monitoring" | "resolved"
export type IncidentImpact = "partial" | "degraded" | "risk" | "delayed" | "none"

export type IncidentEvent = {
  at: string
  actor: string
  action: string
  detail: string | null
}

export type Incident = {
  id: string
  title: string
  severity: IncidentSeverity
  state: IncidentState
  service: string
  env: "production" | "staging" | "dev"
  owner: string | null
  startedAt: string
  detectedAt: string
  acknowledgedAt: string | null
  mitigatedAt: string | null
  resolvedAt: string | null
  updatedAt: string
  impact: IncidentImpact
  impactSummary: string
  affectedSessions: number | null
  affectedRuns: number | null
  responders: { name: string; role: string }[]
  timeline: IncidentEvent[]
  related: { label: string; href: string; detail: string }[]
}

export type IncidentView = "open" | "resolved" | "all"
export type IncidentSortKey = "severity" | "started" | "updated" | "title"
export type IncidentSortDirection = "asc" | "desc"

export type IncidentListState = {
  search: string
  view: IncidentView
  severities: IncidentSeverity[]
  states: IncidentState[]
  owners: string[]
  sort: IncidentSortKey
  direction: IncidentSortDirection
  incident: string
}

export const INCIDENT_VIEWS: IncidentView[] = ["open", "resolved", "all"]
export const INCIDENT_SEVERITIES: IncidentSeverity[] = ["SEV-1", "SEV-2", "SEV-3", "SEV-4"]
export const INCIDENT_STATES: IncidentState[] = ["investigating", "identified", "mitigating", "monitoring", "resolved"]
export const INCIDENT_SORT_KEYS: IncidentSortKey[] = ["severity", "started", "updated", "title"]

export const INCIDENT_STATE_LABELS: Record<IncidentState, string> = {
  investigating: "Investigating",
  identified: "Identified",
  mitigating: "Mitigating",
  monitoring: "Monitoring",
  resolved: "Resolved",
}

export const INCIDENT_IMPACT_LABELS: Record<IncidentImpact, string> = {
  partial: "Partial outage",
  degraded: "Degraded",
  risk: "At risk",
  delayed: "Delayed",
  none: "None observed",
}

export const INCIDENT_SORT_LABELS: Record<IncidentSortKey, string> = {
  severity: "Severity",
  started: "Started",
  updated: "Last update",
  title: "Incident",
}

export const INCIDENT_VIEW_LABELS: Record<IncidentView, string> = {
  open: "Open",
  resolved: "Resolved",
  all: "All",
}

export const INCIDENT_SEVERITY_ORDER: Record<IncidentSeverity, number> = {
  "SEV-1": 0,
  "SEV-2": 1,
  "SEV-3": 2,
  "SEV-4": 3,
}

export const INCIDENT_DEFAULT_SORT_DIRECTION: Record<IncidentSortKey, IncidentSortDirection> = {
  severity: "asc",
  started: "desc",
  updated: "desc",
  title: "asc",
}

export const INCIDENT_OBSERVED_AT = "2026-10-30T15:12:00Z"

export const incidents: Incident[] = [
  {
    id: "inc_2481",
    title: "Elevated proxy 5xx in us-east",
    severity: "SEV-1",
    state: "mitigating",
    service: "llm-proxy",
    env: "production",
    owner: "Mira Chen",
    startedAt: "2026-10-30T14:54:00Z",
    detectedAt: "2026-10-30T14:56:00Z",
    acknowledgedAt: "2026-10-30T14:57:00Z",
    mitigatedAt: "2026-10-30T15:08:00Z",
    resolvedAt: null,
    updatedAt: "2026-10-30T15:08:00Z",
    impact: "partial",
    impactSummary: "Partial · 12 sessions",
    affectedSessions: 12,
    affectedRuns: 284,
    responders: [
      { name: "Mira Chen", role: "Commander" },
      { name: "Jon Park", role: "Communications" },
      { name: "Sam Ortiz", role: "Scribe" },
    ],
    timeline: [
      {
        at: "2026-10-30T14:54:00Z",
        actor: "Mira Chen",
        action: "Declared SEV-1",
        detail: "Proxy 5xx rate crossed 2% for five minutes in us-east.",
      },
      {
        at: "2026-10-30T14:57:00Z",
        actor: "On-call",
        action: "Acknowledged",
        detail: "Incident commander assigned; customer impact under review.",
      },
      {
        at: "2026-10-30T15:01:00Z",
        actor: "Jon Park",
        action: "Status → identified",
        detail: "Connection-pool exhaustion traced to a retry amplification pattern.",
      },
      {
        at: "2026-10-30T15:08:00Z",
        actor: "Mira Chen",
        action: "Mitigation deployed",
        detail: "Retry budget capped and unhealthy upstreams removed from rotation.",
      },
    ],
    related: [
      { label: "Affected runs", href: "/explore?status=error", detail: "284 runs inside the impact window" },
      { label: "Drift signal", href: "/drift", detail: "Retry rate shifted near first occurrence" },
      { label: "Audit trail", href: "/audit", detail: "Status, owner, and severity changes" },
    ],
  },
  {
    id: "inc_2480",
    title: "Context assembly p95 above SLO",
    severity: "SEV-2",
    state: "identified",
    service: "context-assembly",
    env: "production",
    owner: "Jon Park",
    startedAt: "2026-10-30T13:12:00Z",
    detectedAt: "2026-10-30T13:14:00Z",
    acknowledgedAt: "2026-10-30T13:20:00Z",
    mitigatedAt: null,
    resolvedAt: null,
    updatedAt: "2026-10-30T15:02:00Z",
    impact: "degraded",
    impactSummary: "Degraded · 1 tenant",
    affectedSessions: null,
    affectedRuns: 96,
    responders: [
      { name: "Jon Park", role: "Commander" },
      { name: "Sam Ortiz", role: "Scribe" },
    ],
    timeline: [
      {
        at: "2026-10-30T13:12:00Z",
        actor: "Alertmanager",
        action: "Opened",
        detail: "Assembly p95 held above 420 ms for ten minutes.",
      },
      {
        at: "2026-10-30T13:20:00Z",
        actor: "Jon Park",
        action: "Acknowledged",
        detail: "Scoped to one tenant with an unusually large memory budget.",
      },
      {
        at: "2026-10-30T15:02:00Z",
        actor: "Jon Park",
        action: "Note added",
        detail: "Budget tuning tested in staging; production change is pending review.",
      },
    ],
    related: [
      { label: "Affected runs", href: "/explore", detail: "96 runs above the p95 SLO" },
      { label: "Budget", href: "/budgets", detail: "Tenant budget near its ceiling" },
    ],
  },
  {
    id: "inc_2479",
    title: "Auth revocation propagation lag",
    severity: "SEV-2",
    state: "identified",
    service: "auth",
    env: "production",
    owner: "Sam Ortiz",
    startedAt: "2026-10-30T12:06:00Z",
    detectedAt: "2026-10-30T12:09:00Z",
    acknowledgedAt: "2026-10-30T12:15:00Z",
    mitigatedAt: null,
    resolvedAt: null,
    updatedAt: "2026-10-30T14:40:00Z",
    impact: "risk",
    impactSummary: "Risk · 2 tenants",
    affectedSessions: null,
    affectedRuns: null,
    responders: [
      { name: "Sam Ortiz", role: "Commander" },
      { name: "Mira Chen", role: "Security liaison" },
    ],
    timeline: [
      {
        at: "2026-10-30T12:06:00Z",
        actor: "Sam Ortiz",
        action: "Opened",
        detail: "Revoked key still accepted by one cached decision path.",
      },
      {
        at: "2026-10-30T12:15:00Z",
        actor: "Sam Ortiz",
        action: "Acknowledged",
        detail: "Cache invalidation channel is being drained manually.",
      },
      {
        at: "2026-10-30T14:40:00Z",
        actor: "Mira Chen",
        action: "Note added",
        detail: "No tenant data was accessed after revocation; impact stays \"at risk\".",
      },
    ],
    related: [
      { label: "Access", href: "/access", detail: "Key rotation and revocation metadata" },
      { label: "Audit trail", href: "/audit", detail: "Revocation events and cache drains" },
    ],
  },
  {
    id: "inc_2478",
    title: "Memory dedup backlog",
    severity: "SEV-3",
    state: "investigating",
    service: "memory-workers",
    env: "production",
    owner: null,
    startedAt: "2026-10-30T09:38:00Z",
    detectedAt: "2026-10-30T09:41:00Z",
    acknowledgedAt: null,
    mitigatedAt: null,
    resolvedAt: null,
    updatedAt: "2026-10-30T09:41:00Z",
    impact: "none",
    impactSummary: "None observed",
    affectedSessions: null,
    affectedRuns: null,
    responders: [],
    timeline: [
      {
        at: "2026-10-30T09:38:00Z",
        actor: "Worker monitor",
        action: "Opened",
        detail: "Dedup queue depth is 4× the trailing baseline. No retrieval errors yet.",
      },
    ],
    related: [{ label: "Memories", href: "/memories", detail: "Dedup and conflict state" }],
  },
  {
    id: "inc_2477",
    title: "Export worker retry spike",
    severity: "SEV-3",
    state: "investigating",
    service: "export-worker",
    env: "production",
    owner: null,
    startedAt: "2026-10-30T08:44:00Z",
    detectedAt: "2026-10-30T08:46:00Z",
    acknowledgedAt: null,
    mitigatedAt: null,
    resolvedAt: null,
    updatedAt: "2026-10-30T08:46:00Z",
    impact: "none",
    impactSummary: "None observed",
    affectedSessions: null,
    affectedRuns: null,
    responders: [],
    timeline: [
      {
        at: "2026-10-30T08:44:00Z",
        actor: "Worker monitor",
        action: "Opened",
        detail: "Retry rate doubled after a provider timeout burst.",
      },
    ],
    related: [{ label: "Audit trail", href: "/audit", detail: "Export job outcomes" }],
  },
  {
    id: "inc_2476",
    title: "ClickHouse ingest delay",
    severity: "SEV-3",
    state: "monitoring",
    service: "analytics-ingest",
    env: "production",
    owner: "Sam Ortiz",
    startedAt: "2026-10-30T06:31:00Z",
    detectedAt: "2026-10-30T06:34:00Z",
    acknowledgedAt: "2026-10-30T06:40:00Z",
    mitigatedAt: "2026-10-30T08:05:00Z",
    resolvedAt: null,
    updatedAt: "2026-10-30T12:10:00Z",
    impact: "delayed",
    impactSummary: "Delayed · 12m",
    affectedSessions: null,
    affectedRuns: null,
    responders: [
      { name: "Sam Ortiz", role: "Commander" },
      { name: "Jon Park", role: "Scribe" },
    ],
    timeline: [
      {
        at: "2026-10-30T06:31:00Z",
        actor: "Ingest monitor",
        action: "Opened",
        detail: "Replication lag crossed 10 minutes.",
      },
      {
        at: "2026-10-30T08:05:00Z",
        actor: "Sam Ortiz",
        action: "Mitigated",
        detail: "Ingest batch size reduced; lag is falling and remains monitored.",
      },
    ],
    related: [
      { label: "Analytics", href: "/analytics", detail: "Spend windows may lag the canonical store" },
      { label: "Evidence", href: "/evidence", detail: "Projection delay is not evidence loss" },
    ],
  },
  {
    id: "inc_2475",
    title: "Embedding queue saturation",
    severity: "SEV-3",
    state: "investigating",
    service: "embedding-workers",
    env: "production",
    owner: "Jon Park",
    startedAt: "2026-10-30T02:47:00Z",
    detectedAt: "2026-10-30T02:51:00Z",
    acknowledgedAt: "2026-10-30T07:12:00Z",
    mitigatedAt: null,
    resolvedAt: null,
    updatedAt: "2026-10-30T11:30:00Z",
    impact: "degraded",
    impactSummary: "Degraded · 1 tenant",
    affectedSessions: null,
    affectedRuns: null,
    responders: [{ name: "Jon Park", role: "Commander" }],
    timeline: [
      {
        at: "2026-10-30T02:47:00Z",
        actor: "Queue monitor",
        action: "Opened",
        detail: "Embedding queue depth passed the scale-out threshold.",
      },
      {
        at: "2026-10-30T07:12:00Z",
        actor: "Jon Park",
        action: "Acknowledged",
        detail: "Capacity is being raised; one tenant is rate limited while it drains.",
      },
    ],
    related: [{ label: "Memories", href: "/memories", detail: "Embedding freshness per memory" }],
  },
  {
    id: "inc_2474",
    title: "Console stale cache banner",
    severity: "SEV-4",
    state: "monitoring",
    service: "console",
    env: "production",
    owner: "Mira Chen",
    startedAt: "2026-10-28T16:20:00Z",
    detectedAt: "2026-10-28T16:24:00Z",
    acknowledgedAt: "2026-10-28T16:40:00Z",
    mitigatedAt: "2026-10-28T17:05:00Z",
    resolvedAt: null,
    updatedAt: "2026-10-29T09:00:00Z",
    impact: "none",
    impactSummary: "None observed",
    affectedSessions: null,
    affectedRuns: null,
    responders: [{ name: "Mira Chen", role: "Commander" }],
    timeline: [
      {
        at: "2026-10-28T16:20:00Z",
        actor: "Mira Chen",
        action: "Opened",
        detail: "Banner appeared after a read-model deploy and did not clear.",
      },
      {
        at: "2026-10-28T17:05:00Z",
        actor: "Mira Chen",
        action: "Mitigated",
        detail: "Banner copy corrected; a follow-up is tracking the cache key.",
      },
    ],
    related: [{ label: "Platform", href: "/platform", detail: "Read-model freshness" }],
  },
  {
    id: "inc_2473",
    title: "Provider latency warning",
    severity: "SEV-3",
    state: "monitoring",
    service: "llm-proxy",
    env: "production",
    owner: "Mira Chen",
    startedAt: "2026-10-29T10:40:00Z",
    detectedAt: "2026-10-29T10:42:00Z",
    acknowledgedAt: null,
    mitigatedAt: "2026-10-29T12:30:00Z",
    resolvedAt: null,
    updatedAt: "2026-10-29T12:30:00Z",
    impact: "none",
    impactSummary: "None observed",
    affectedSessions: null,
    affectedRuns: null,
    responders: [],
    timeline: [
      {
        at: "2026-10-29T10:40:00Z",
        actor: "Provider probe",
        action: "Opened",
        detail: "Google p95 latency stayed above the warning band for 30 minutes.",
      },
      {
        at: "2026-10-29T12:30:00Z",
        actor: "Routing policy",
        action: "Mitigated",
        detail: "Traffic shifted to the fallback chain; no errors were observed.",
      },
    ],
    related: [{ label: "Providers", href: "/providers", detail: "Declared and observed provider health" }],
  },
  {
    id: "inc_2472",
    title: "Memory retrieval timeouts in eu-west",
    severity: "SEV-2",
    state: "resolved",
    service: "memory-api",
    env: "production",
    owner: "Jon Park",
    startedAt: "2026-10-29T19:05:00Z",
    detectedAt: "2026-10-29T19:07:00Z",
    acknowledgedAt: "2026-10-29T19:10:00Z",
    mitigatedAt: "2026-10-29T20:12:00Z",
    resolvedAt: "2026-10-29T21:10:00Z",
    updatedAt: "2026-10-29T21:10:00Z",
    impact: "degraded",
    impactSummary: "Degraded · 1 tenant",
    affectedSessions: 8,
    affectedRuns: 41,
    responders: [{ name: "Jon Park", role: "Commander" }],
    timeline: [
      {
        at: "2026-10-29T19:05:00Z",
        actor: "Alertmanager",
        action: "Opened",
        detail: "Retrieval p99 crossed the tenant SLO.",
      },
      {
        at: "2026-10-29T21:10:00Z",
        actor: "Jon Park",
        action: "Resolved",
        detail: "A cold vector index was warmed; no follow-up required.",
      },
    ],
    related: [{ label: "Sessions", href: "/sessions", detail: "8 sessions inside the impact window" }],
  },
  {
    id: "inc_2471",
    title: "Outbox consumer lag",
    severity: "SEV-3",
    state: "resolved",
    service: "evidence-relay",
    env: "production",
    owner: "Sam Ortiz",
    startedAt: "2026-10-29T09:40:00Z",
    detectedAt: "2026-10-29T09:44:00Z",
    acknowledgedAt: "2026-10-29T09:52:00Z",
    mitigatedAt: "2026-10-29T12:02:00Z",
    resolvedAt: "2026-10-29T14:02:00Z",
    updatedAt: "2026-10-29T14:02:00Z",
    impact: "delayed",
    impactSummary: "Delayed · 26m",
    affectedSessions: null,
    affectedRuns: null,
    responders: [{ name: "Sam Ortiz", role: "Commander" }],
    timeline: [
      {
        at: "2026-10-29T09:40:00Z",
        actor: "Relay monitor",
        action: "Opened",
        detail: "Consumer lag passed 20 minutes.",
      },
      {
        at: "2026-10-29T14:02:00Z",
        actor: "Sam Ortiz",
        action: "Resolved",
        detail: "Consumer restarted with a larger lease; lag returned to zero.",
      },
    ],
    related: [{ label: "Evidence", href: "/evidence", detail: "Relay state and tombstones" }],
  },
  {
    id: "inc_2470",
    title: "Proxy retry storm after deploy",
    severity: "SEV-2",
    state: "resolved",
    service: "llm-proxy",
    env: "production",
    owner: "Mira Chen",
    startedAt: "2026-10-28T17:20:00Z",
    detectedAt: "2026-10-28T17:22:00Z",
    acknowledgedAt: "2026-10-28T17:25:00Z",
    mitigatedAt: "2026-10-28T18:10:00Z",
    resolvedAt: "2026-10-28T18:40:00Z",
    updatedAt: "2026-10-28T18:40:00Z",
    impact: "partial",
    impactSummary: "Partial · 4 sessions",
    affectedSessions: 4,
    affectedRuns: 63,
    responders: [{ name: "Mira Chen", role: "Commander" }],
    timeline: [
      {
        at: "2026-10-28T17:20:00Z",
        actor: "Rollout monitor",
        action: "Opened",
        detail: "Retry rate tripled within two minutes of a proxy rollout.",
      },
      {
        at: "2026-10-28T18:40:00Z",
        actor: "Mira Chen",
        action: "Resolved",
        detail: "Rollout rolled back; retry budget restored.",
      },
    ],
    related: [{ label: "Platform", href: "/platform", detail: "Deployment history" }],
  },
  {
    id: "inc_2469",
    title: "Docs link 404 in console footer",
    severity: "SEV-4",
    state: "resolved",
    service: "console",
    env: "production",
    owner: "Sam Ortiz",
    startedAt: "2026-10-27T10:50:00Z",
    detectedAt: "2026-10-27T10:52:00Z",
    acknowledgedAt: "2026-10-27T11:00:00Z",
    mitigatedAt: "2026-10-27T11:10:00Z",
    resolvedAt: "2026-10-27T11:15:00Z",
    updatedAt: "2026-10-27T11:15:00Z",
    impact: "none",
    impactSummary: "None observed",
    affectedSessions: null,
    affectedRuns: null,
    responders: [{ name: "Sam Ortiz", role: "Commander" }],
    timeline: [
      {
        at: "2026-10-27T10:50:00Z",
        actor: "Sam Ortiz",
        action: "Opened",
        detail: "Footer documentation link pointed at a removed route.",
      },
      {
        at: "2026-10-27T11:15:00Z",
        actor: "Sam Ortiz",
        action: "Resolved",
        detail: "Link now points at the published docs index.",
      },
    ],
    related: [],
  },
]

export function isOpenIncident(incident: Incident): boolean {
  return incident.state !== "resolved"
}

export function incidentMatches(incident: Incident, state: IncidentListState): boolean {
  if (state.view === "open" && !isOpenIncident(incident)) return false
  if (state.view === "resolved" && isOpenIncident(incident)) return false
  if (state.severities.length && !state.severities.includes(incident.severity)) return false
  if (state.states.length && !state.states.includes(incident.state)) return false
  if (state.owners.length) {
    const owner = incident.owner ?? "Unassigned"
    if (!state.owners.includes(owner)) return false
  }
  const search = state.search.trim().toLowerCase()
  if (search) {
    const haystack = [incident.id, incident.title, incident.service, incident.owner ?? "unassigned", incident.env]
      .join(" ")
      .toLowerCase()
    if (!haystack.includes(search)) return false
  }
  return true
}

export function sortIncidents(rows: Incident[], key: IncidentSortKey, direction: IncidentSortDirection): Incident[] {
  const multiplier = direction === "asc" ? 1 : -1
  return [...rows].sort((left, right) => {
    if (key === "severity") {
      return multiplier * (INCIDENT_SEVERITY_ORDER[left.severity] - INCIDENT_SEVERITY_ORDER[right.severity])
    }
    if (key === "title") return multiplier * left.title.localeCompare(right.title)
    const leftTime = Date.parse(key === "started" ? left.startedAt : left.updatedAt)
    const rightTime = Date.parse(key === "started" ? right.startedAt : right.updatedAt)
    return multiplier * (leftTime - rightTime)
  })
}

export function incidentOwners(): string[] {
  return [...new Set(incidents.map((incident) => incident.owner ?? "Unassigned"))].sort((a, b) => a.localeCompare(b))
}

export function incidentSummary() {
  const open = incidents.filter(isOpenIncident)
  const unacknowledged = open.filter((incident) => !incident.acknowledgedAt)
  const resolved = incidents.filter((incident) => incident.state === "resolved")
  const oldest = open.reduce<Incident | null>(
    (current, incident) =>
      !current || Date.parse(incident.startedAt) < Date.parse(current.startedAt) ? incident : current,
    null,
  )
  return {
    open: open.length,
    sev1: open.filter((incident) => incident.severity === "SEV-1").length,
    sev2: open.filter((incident) => incident.severity === "SEV-2").length,
    unacknowledged: unacknowledged.length,
    oldest,
    resolved: resolved.length,
  }
}

export type IncidentAttention = {
  id: string
  title: string
  reason: string
  detail: string
  tone: "critical" | "warning" | "neutral"
  incidentId: string
}

export function incidentAttention(): IncidentAttention[] {
  const rows: IncidentAttention[] = []
  for (const incident of incidents.filter(isOpenIncident)) {
    if (!incident.acknowledgedAt) {
      rows.push({
        id: `${incident.id}-ack`,
        title: incident.title,
        reason: "Unacknowledged",
        detail: `Opened ${incident.id} · no owner has acknowledged it`,
        tone: incident.severity === "SEV-1" || incident.severity === "SEV-2" ? "critical" : "warning",
        incidentId: incident.id,
      })
    } else if (!incident.owner) {
      rows.push({
        id: `${incident.id}-owner`,
        title: incident.title,
        reason: "Unowned",
        detail: `Opened ${incident.id} · no incident commander assigned`,
        tone: "warning",
        incidentId: incident.id,
      })
    } else if (incident.severity === "SEV-1" && incident.state !== "mitigating") {
      rows.push({
        id: `${incident.id}-sev1`,
        title: incident.title,
        reason: "SEV-1 without mitigation",
        detail: `Opened ${incident.id} · ${incident.impactSummary}`,
        tone: "critical",
        incidentId: incident.id,
      })
    } else if (Date.parse(INCIDENT_OBSERVED_AT) - Date.parse(incident.updatedAt) > 6 * 60 * 60 * 1000) {
      rows.push({
        id: `${incident.id}-stale`,
        title: incident.title,
        reason: "Stale update",
        detail: `Opened ${incident.id} · no update for over six hours`,
        tone: "warning",
        incidentId: incident.id,
      })
    }
  }
  const order = { critical: 0, warning: 1, neutral: 2 }
  return rows.sort((left, right) => order[left.tone] - order[right.tone]).slice(0, 6)
}

export function incidentById(id: string): Incident | null {
  return incidents.find((incident) => incident.id === id) ?? null
}

const MINUTE = 60_000
const HOUR = 60 * MINUTE
const DAY = 24 * HOUR

/** Incident age, keeping hours once past a day so "1d 22h" never reads as "1d". */
export function formatIncidentAge(start: string, end: string | null): string {
  const from = Date.parse(start)
  const to = end ? Date.parse(end) : Date.parse(INCIDENT_OBSERVED_AT)
  if (!Number.isFinite(from) || !Number.isFinite(to) || to < from) return "—"
  const delta = to - from
  if (delta < HOUR) return `${Math.max(1, Math.round(delta / MINUTE))}m`
  if (delta < DAY) return `${Math.floor(delta / HOUR)}h`
  const days = Math.floor(delta / DAY)
  const hours = Math.floor((delta % DAY) / HOUR)
  return hours ? `${days}d ${hours}h` : `${days}d`
}

export function emptyIncidentListState(): IncidentListState {
  return {
    search: "",
    view: "open",
    severities: [],
    states: [],
    owners: [],
    sort: "severity",
    direction: "asc",
    incident: "",
  }
}

function firstValue(value: unknown): string {
  if (typeof value === "string") return value
  if (Array.isArray(value)) return value.find((entry): entry is string => typeof entry === "string") ?? ""
  return ""
}

function listValues(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : [value]
  return raw
    .filter((entry): entry is string => typeof entry === "string")
    .flatMap((entry) => entry.split(","))
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function allowed<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

export function parseIncidentQuery(query: Record<string, unknown>): IncidentListState {
  const state = emptyIncidentListState()
  state.search = firstValue(query.q).trim().slice(0, 120)
  const view = firstValue(query.view)
  if (allowed(view, INCIDENT_VIEWS)) state.view = view
  state.severities = [...new Set(listValues(query.severity).filter((entry) => allowed(entry, INCIDENT_SEVERITIES)))]
  state.states = [...new Set(listValues(query.state).filter((entry) => allowed(entry, INCIDENT_STATES)))]
  state.owners = [...new Set(listValues(query.owner))].slice(0, 12)
  const sort = firstValue(query.sort)
  if (allowed(sort, INCIDENT_SORT_KEYS)) state.sort = sort
  const direction = firstValue(query.dir)
  state.direction = direction === "asc" || direction === "desc" ? direction : INCIDENT_DEFAULT_SORT_DIRECTION[state.sort]
  const incident = firstValue(query.incident)
  state.incident = incident && incidentById(incident) ? incident : ""
  return state
}

export function serializeIncidentQuery(state: IncidentListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.search.trim()) query.set("q", state.search.trim().slice(0, 120))
  if (state.view !== "open") query.set("view", state.view)
  if (state.severities.length) query.set("severity", state.severities.join(","))
  if (state.states.length) query.set("state", state.states.join(","))
  if (state.owners.length) query.set("owner", state.owners.join(","))
  if (state.sort !== "severity") query.set("sort", state.sort)
  if (state.direction !== INCIDENT_DEFAULT_SORT_DIRECTION[state.sort]) query.set("dir", state.direction)
  if (state.incident) query.set("incident", state.incident)
  return query
}

export function incidentHref(state: IncidentListState, incidentId?: string): string {
  const next = { ...state, incident: incidentId ?? state.incident }
  const query = serializeIncidentQuery(next).toString()
  return query ? `/incidents?${query}` : "/incidents"
}
