export const SETTINGS_SECTIONS = [
  "organization",
  "environments",
  "agent-defaults",
  "data-mode",
  "read-only",
  "retention",
  "privacy",
  "evidence-relay",
  "display",
  "api-origin",
  "danger-zone",
] as const

export type SettingsSection = (typeof SETTINGS_SECTIONS)[number]

export const SETTINGS_CATEGORIES = [
  {
    id: "general",
    label: "General",
    sections: ["organization", "environments", "agent-defaults", "display"],
  },
  {
    id: "access",
    label: "Access",
    sections: ["data-mode", "read-only", "danger-zone"],
  },
  {
    id: "data",
    label: "Data",
    sections: ["retention", "privacy", "evidence-relay", "api-origin"],
  },
] as const

export type SettingsCategory = (typeof SETTINGS_CATEGORIES)[number]["id"]

export function settingsCategoryFor(section: SettingsSection): SettingsCategory {
  return SETTINGS_CATEGORIES.find((category) => (category.sections as readonly string[]).includes(section))?.id ?? "general"
}

export function nextSettingsCategory(category: SettingsCategory, delta: number): SettingsCategory {
  const index = SETTINGS_CATEGORIES.findIndex((entry) => entry.id === category)
  return SETTINGS_CATEGORIES[(index + delta + SETTINGS_CATEGORIES.length) % SETTINGS_CATEGORIES.length]!.id
}

export function firstSectionForCategory(category: SettingsCategory): SettingsSection {
  return SETTINGS_CATEGORIES.find((entry) => entry.id === category)?.sections[0] as SettingsSection
}

export type SettingsRow = {
  label: string
  value: string
  hint: string
  owner: string
  changedAt: string
  audit?: string
}

export const SETTINGS_ORGANIZATION: SettingsRow[] = [
  {
    label: "Organization name",
    value: "Ibex Demo",
    hint: "Shown in the console and written into audit records.",
    owner: "Workspace admin",
    changedAt: "2026-10-18T11:22:00Z",
    audit: "evt_4c81ee",
  },
  {
    label: "Slug",
    value: "ibex-demo",
    hint: "Stable identifier used by links and API scope.",
    owner: "Workspace admin",
    changedAt: "2026-09-02T08:14:00Z",
    audit: "evt_1a0712",
  },
  {
    label: "Status",
    value: "Active",
    hint: "Organization lifecycle state. Suspension and deletion are separate, audited operations.",
    owner: "Platform",
    changedAt: "2026-07-18T16:40:00Z",
    audit: "evt_77b031",
  },
]

export const SETTINGS_ENVIRONMENTS = [
  { name: "Production", traffic: "64% of traffic", state: "active", owner: "SRE", changedAt: "2026-10-21T10:00:00Z" },
  { name: "Staging", traffic: "31% of traffic", state: "active", owner: "Platform", changedAt: "2026-10-12T10:00:00Z" },
  { name: "Development", traffic: "5% of traffic", state: "active", owner: "Engineering", changedAt: "2026-09-27T10:00:00Z" },
]

export const SETTINGS_RETENTION: SettingsRow[] = [
  {
    label: "Trace metadata",
    value: "90 days",
    hint: "Deleted by policy after the window.",
    owner: "Security",
    changedAt: "2026-10-18T10:00:00Z",
    audit: "evt_7b30d2",
  },
  {
    label: "Memory content",
    value: "30 days",
    hint: "Session scope plus retention policy.",
    owner: "Security",
    changedAt: "2026-10-18T10:00:00Z",
    audit: "evt_7b30d2",
  },
  {
    label: "Audit events",
    value: "7 years",
    hint: "Append-only; deletion is not a console action.",
    owner: "Compliance",
    changedAt: "2026-08-04T10:00:00Z",
    audit: "evt_5b90c2",
  },
  {
    label: "Evidence records",
    value: "1 year",
    hint: "A tombstone keeps the deletion basis after content is gone.",
    owner: "Compliance",
    changedAt: "2026-08-04T10:00:00Z",
    audit: "evt_5b90c2",
  },
]

export const SETTINGS_AGENT_DEFAULTS: SettingsRow[] = [
  {
    label: "Default model",
    value: "gpt-4.1",
    hint: "Model a new agent uses unless it declares its own.",
    owner: "Platform",
    changedAt: "2026-10-21T10:00:00Z",
    audit: "evt_9a21c4",
  },
  {
    label: "Default provider",
    value: "OpenAI",
    hint: "Provider route used when a model is available in more than one place.",
    owner: "Platform",
    changedAt: "2026-10-21T10:00:00Z",
    audit: "evt_9a21c4",
  },
  {
    label: "Memory injection",
    value: "On · top 8",
    hint: "Maximum memories placed in a normal turn context.",
    owner: "ML platform",
    changedAt: "2026-10-18T15:30:00Z",
    audit: "evt_4b72d1",
  },
  {
    label: "Context budget",
    value: "128,000 tokens",
    hint: "Ceiling for directive, memory, and conversation text.",
    owner: "Platform",
    changedAt: "2026-10-12T09:00:00Z",
    audit: "evt_2c19ee",
  },
  {
    label: "Drift sensitivity",
    value: "0.60",
    hint: "Lower values open a drift signal sooner.",
    owner: "ML platform",
    changedAt: "2026-10-03T12:00:00Z",
    audit: "evt_7e1a02",
  },
]

export const SETTINGS_PRIVACY: SettingsRow[] = [
  {
    label: "Default capture mode",
    value: "metadata_only",
    hint: "Applies when no agent-specific capture policy matches. Raw prompt and completion content is not stored.",
    owner: "Security",
    changedAt: "2026-10-24T09:30:00Z",
    audit: "evt_7b30d2",
  },
  {
    label: "Agent capture overrides",
    value: "1 agent",
    hint: "A more specific row wins over the organization default. Priority resolves ties.",
    owner: "Security",
    changedAt: "2026-10-24T09:30:00Z",
    audit: "evt_7b30d2",
  },
  {
    label: "PII detection",
    value: "Presidio · enabled",
    hint: "Analyzer findings are routed by confidence before any redaction is applied.",
    owner: "Security",
    changedAt: "2026-10-18T10:00:00Z",
    audit: "evt_4c81ee",
  },
  {
    label: "Redaction threshold",
    value: "0.60 confidence",
    hint: "Findings below the threshold quarantine the record instead of being silently redacted or allowed.",
    owner: "Security",
    changedAt: "2026-10-18T10:00:00Z",
    audit: "evt_4c81ee",
  },
  {
    label: "Read-path PII re-check",
    value: "Tier-1 structured",
    hint: "Hydrated search and hot-cache results are re-checked before they are returned.",
    owner: "Platform",
    changedAt: "2026-10-21T10:00:00Z",
    audit: "evt_9a21c4",
  },
  {
    label: "Redaction proof version",
    value: "session-metadata-allowlist/v1",
    hint: "The sanitizer version recorded on redacted session evidence rows.",
    owner: "Platform",
    changedAt: "2026-10-21T10:00:00Z",
    audit: "evt_9a21c4",
  },
  {
    label: "Active legal holds",
    value: "1 hold",
    hint: "mem_44b1e2 · set by Compliance on 2026-10-29. Deletion stays blocked until the hold is cleared.",
    owner: "Compliance",
    changedAt: "2026-10-29T15:40:00Z",
    audit: "evt_c2806b",
  },
]

export const SETTINGS_AUTHORITY = [
  {
    label: "Data mode",
    value: "Illustrative",
    detail: "No live tenant data plane is attached to this console.",
    tone: "warn" as const,
  },
  {
    label: "Read-only mode",
    value: "Enforced",
    detail: "Write controls stay disabled until their contracts exist.",
    tone: "ok" as const,
  },
  {
    label: "Authentication",
    value: "Demo session",
    detail: "Proxy-injected cookie; AuthService login is not connected.",
    tone: "warn" as const,
  },
  {
    label: "Mutation path",
    value: "Unavailable",
    detail: "Idempotency, approval, rollback, and audit are not implemented.",
    tone: "crit" as const,
  },
  {
    label: "Presentation flags",
    value: "Non-authoritative",
    detail: "Theme and density never grant tenant authority.",
    tone: "neutral" as const,
  },
]

export const SETTINGS_EVIDENCE = [
  { label: "Canonical store", value: "PostgreSQL", detail: "Evidence and run records remain authoritative.", owner: "Platform", changedAt: "2026-10-18T10:00:00Z" },
  { label: "Analytics projection", value: "ClickHouse", detail: "Derived; cannot prove billing, deletion, or audit completeness.", owner: "Data", changedAt: "2026-10-18T10:00:00Z" },
  { label: "Relay path", value: "Outbox → consumer", detail: "Lease, retry, and terminal state are explicit.", owner: "Platform", changedAt: "2026-10-21T10:00:00Z" },
  { label: "Capture modes", value: "6 registered", detail: "Outbox, span batch, queue, stream, webhook, manual import.", owner: "Platform", changedAt: "2026-10-21T10:00:00Z" },
  { label: "Tombstones", value: "Preserved", detail: "Deletion basis retained; content is not.", owner: "Security", changedAt: "2026-10-12T10:00:00Z" },
]

export const SETTINGS_ORIGINS = [
  { name: "Operator API", endpoint: "https://127.0.0.1:3285", state: "healthy", detail: "18ms · last observed 12s ago" },
  { name: "SSE event stream", endpoint: "/api/operator/events", state: "healthy", detail: "open · last event 2s ago" },
  { name: "Provider gateway", endpoint: "routed · 6 providers", state: "degraded", detail: "1 upstream elevated latency" },
  { name: "Console origin", endpoint: "http://127.0.0.1:3287", state: "healthy", detail: "read-only · request traced" },
]

export const SETTINGS_DANGER = [
  { label: "Export all organization data", actionLabel: "Export data", reason: "Evidence bundle contract is not accepted." },
  { label: "Rotate all credentials", actionLabel: "Rotate credentials", reason: "AuthService rotation flow is deferred." },
  { label: "Delete organization", actionLabel: "Delete organization", reason: "Legal hold and deletion guarantees are not connected." },
]

export function isSettingsSection(value: string): value is SettingsSection {
  return (SETTINGS_SECTIONS as readonly string[]).includes(value)
}
