/**
 * Illustrative MCP tool fixtures for Connect › MCP tools.
 *
 * The tool catalogue, schemas, and invocation samples are design fixtures. No
 * tool is invoked from the console and no live catalogue is claimed.
 */

export type ToolEffect = "read-only" | "mutating" | "external"
export type ToolStatus = "enabled" | "disabled"
export type ToolIdempotency = "yes" | "keyed" | "no"
export type ToolApproval = "never" | "step-up" | "policy"
export type ToolTab = "tools" | "invocations" | "permissions"
export type ToolSortKey = "name" | "effect" | "status"
export type ToolSortDirection = "asc" | "desc"
export type ToolResult = "ok" | "denied" | "error"

export type ToolInvocation = {
  id: string
  tool: string
  actor: string
  at: string
  latencyMs: number
  result: ToolResult
}

export type Tool = {
  name: string
  server: string
  description: string
  effect: ToolEffect
  idempotency: ToolIdempotency
  approval: ToolApproval
  status: ToolStatus
  schemaHash: string
  schemaVersion: string
  params: { name: string; type: string; required: boolean; note?: string }[]
  bounds: { input: string; output: string; timeout: string; idempotencyKey: string }
  transport: string
  auth: string
  origin: string
  invocations: ToolInvocation[]
}

export type ToolListState = {
  search: string
  tab: ToolTab
  effects: ToolEffect[]
  statuses: ToolStatus[]
  sort: ToolSortKey
  direction: ToolSortDirection
  tool: string
}

export const TOOL_TABS: { id: ToolTab; label: string }[] = [
  { id: "tools", label: "Tools" },
  { id: "invocations", label: "Recent invocations" },
  { id: "permissions", label: "Permissions" },
]

export const TOOL_EFFECTS: ToolEffect[] = ["read-only", "mutating", "external"]
export const TOOL_STATUSES: ToolStatus[] = ["enabled", "disabled"]
export const TOOL_SORT_KEYS: ToolSortKey[] = ["name", "effect", "status"]

export const TOOL_EFFECT_LABELS: Record<ToolEffect, string> = {
  "read-only": "Read-only",
  mutating: "Mutating",
  external: "External",
}

export const TOOL_IDEMPOTENCY_LABELS: Record<ToolIdempotency, string> = {
  yes: "Yes",
  keyed: "Keyed",
  no: "No",
}

export const TOOL_APPROVAL_LABELS: Record<ToolApproval, string> = {
  never: "Not required",
  "step-up": "Step-up required",
  policy: "Policy decides",
}

export const TOOL_STATUS_LABELS: Record<ToolStatus, string> = {
  enabled: "Enabled",
  disabled: "Disabled",
}

export const TOOL_SORT_LABELS: Record<ToolSortKey, string> = {
  name: "Tool",
  effect: "Side effect",
  status: "Status",
}

export const TOOL_DEFAULT_SORT_DIRECTION: Record<ToolSortKey, ToolSortDirection> = {
  name: "asc",
  effect: "asc",
  status: "asc",
}

export const TOOL_OBSERVED_AT = "2026-10-30T15:12:00Z"

function invocation(tool: string, actor: string, at: string, latencyMs: number, result: ToolResult): ToolInvocation {
  return { id: `inv_${tool}_${at.replace(/\W/g, "").slice(4, 14)}`, tool, actor, at, latencyMs, result }
}

export const tools: Tool[] = [
  {
    name: "search_workspace",
    server: "workspace",
    description: "Full-text search across workspace documents visible to the calling agent.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:4c81d9a0e3",
    schemaVersion: "2026-09-14",
    params: [
      { name: "query", type: "string", required: true },
      { name: "limit", type: "integer", required: false, note: "1–50, default 10" },
    ],
    bounds: { input: "8KB · 2 fields", output: "Search hits + snippets", timeout: "10s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [invocation("search_workspace", "support-triage", "2026-10-30T15:10:00Z", 84, "ok")],
  },
  {
    name: "get_workspace_memory",
    server: "memory",
    description: "Read one memory by id, including its scope and provenance.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:9f2a71c0b4",
    schemaVersion: "2026-09-14",
    params: [{ name: "memory_id", type: "string", required: true }],
    bounds: { input: "2KB · 1 field", output: "Memory record", timeout: "8s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [invocation("get_workspace_memory", "support-triage", "2026-10-30T15:09:00Z", 112, "ok")],
  },
  {
    name: "create_export",
    server: "data",
    description: "Create a signed export of workspace data for one date range.",
    effect: "mutating",
    idempotency: "keyed",
    approval: "step-up",
    status: "enabled",
    schemaHash: "sha256:4c81ee21a7",
    schemaVersion: "2026-10-02",
    params: [
      { name: "workspace_id", type: "string", required: true, note: "^ws_[a-z0-9]+$" },
      { name: "format", type: "string", required: true, note: "csv | jsonl" },
      { name: "redact_pii", type: "boolean", required: false, note: "default true" },
    ],
    bounds: { input: "16KB · 8 fields", output: "export_id + signed URL", timeout: "30s", idempotencyKey: "Required" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [invocation("create_export", "billing-analyst", "2026-10-30T15:02:00Z", 1200, "ok")],
  },
  {
    name: "notify_channel",
    server: "notifications",
    description: "Send a message to an operator channel through the notification connector.",
    effect: "external",
    idempotency: "keyed",
    approval: "policy",
    status: "enabled",
    schemaHash: "sha256:1a0712f9c2",
    schemaVersion: "2026-08-21",
    params: [
      { name: "channel", type: "string", required: true },
      { name: "text", type: "string", required: true, note: "max 2,000 chars" },
    ],
    bounds: { input: "4KB · 2 fields", output: "Delivery receipt", timeout: "15s", idempotencyKey: "Required" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [invocation("notify_channel", "policy-engine", "2026-10-30T14:58:00Z", 240, "denied")],
  },
  {
    name: "redact_pii",
    server: "content",
    description: "Replace detected personal data in a stored record with redaction markers.",
    effect: "mutating",
    idempotency: "yes",
    approval: "step-up",
    status: "enabled",
    schemaHash: "sha256:77b031d8aa",
    schemaVersion: "2026-09-30",
    params: [
      { name: "record_id", type: "string", required: true },
      { name: "categories", type: "array", required: true },
    ],
    bounds: { input: "8KB · 2 fields", output: "Redaction summary", timeout: "20s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "delete_workspace",
    server: "admin",
    description: "Permanently delete a workspace and every record inside it.",
    effect: "mutating",
    idempotency: "no",
    approval: "step-up",
    status: "disabled",
    schemaHash: "sha256:2e44f1a06b",
    schemaVersion: "2026-07-18",
    params: [{ name: "workspace_id", type: "string", required: true }],
    bounds: { input: "1KB · 1 field", output: "Deletion receipt", timeout: "60s", idempotencyKey: "Not supported" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "list_exports",
    server: "data",
    description: "List exports created for this workspace, newest first.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:5b90c2a4d1",
    schemaVersion: "2026-10-02",
    params: [{ name: "workspace_id", type: "string", required: true }],
    bounds: { input: "1KB · 1 field", output: "Export rows", timeout: "10s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "search_memory",
    server: "memory",
    description: "Vector search across memories visible to the calling agent.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:7b30d2c9e8",
    schemaVersion: "2026-09-14",
    params: [
      { name: "query", type: "string", required: true },
      { name: "scope", type: "string", required: false },
    ],
    bounds: { input: "8KB · 2 fields", output: "Memory hits", timeout: "12s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "update_workspace_settings",
    server: "workspace",
    description: "Change workspace-level settings such as retention or display defaults.",
    effect: "mutating",
    idempotency: "keyed",
    approval: "step-up",
    status: "enabled",
    schemaHash: "sha256:81c0a4b7df",
    schemaVersion: "2026-10-12",
    params: [
      { name: "workspace_id", type: "string", required: true },
      { name: "settings", type: "object", required: true },
    ],
    bounds: { input: "32KB · 2 fields", output: "Updated settings", timeout: "20s", idempotencyKey: "Required" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "list_workspace_members",
    server: "workspace",
    description: "List members, roles, and scopes for a workspace.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:c81e2b30f7",
    schemaVersion: "2026-08-21",
    params: [{ name: "workspace_id", type: "string", required: true }],
    bounds: { input: "1KB · 1 field", output: "Member rows", timeout: "10s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "get_audit_event",
    server: "admin",
    description: "Read one immutable audit event by id.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:a041f8b6c0",
    schemaVersion: "2026-07-18",
    params: [{ name: "event_id", type: "string", required: true }],
    bounds: { input: "1KB · 1 field", output: "Audit event", timeout: "8s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [],
  },
  {
    name: "read_provider_health",
    server: "admin",
    description: "Read declared and observed health for configured model providers.",
    effect: "read-only",
    idempotency: "yes",
    approval: "never",
    status: "enabled",
    schemaHash: "sha256:d9a0c4e1b3",
    schemaVersion: "2026-07-18",
    params: [],
    bounds: { input: "— · 0 fields", output: "Provider health rows", timeout: "8s", idempotencyKey: "Not needed" },
    transport: "streamable HTTP",
    auth: "OAuth 2.1 · PKCE",
    origin: "pinned · 5m skew",
    invocations: [invocation("read_provider_health", "console", "2026-10-30T15:11:00Z", 68, "ok")],
  },
]

export const toolInvocations: ToolInvocation[] = tools
  .flatMap((tool) => tool.invocations)
  .sort((left, right) => Date.parse(right.at) - Date.parse(left.at))

export const TOOL_PERMISSIONS = ["List tools", "Read schema", "Invoke read", "Invoke mutate"] as const
export const TOOL_ROLES = ["Viewer", "Analyst", "Operator", "Admin"] as const

export const TOOL_PERMISSION_MATRIX: Record<(typeof TOOL_ROLES)[number], boolean[]> = {
  Viewer: [true, true, true, false],
  Analyst: [true, true, true, false],
  Operator: [true, true, true, true],
  Admin: [true, true, true, true],
}

export function toolByName(name: string): Tool | null {
  return tools.find((tool) => tool.name === name) ?? null
}

export function toolMatches(tool: Tool, state: ToolListState): boolean {
  if (state.effects.length && !state.effects.includes(tool.effect)) return false
  if (state.statuses.length && !state.statuses.includes(tool.status)) return false
  const search = state.search.trim().toLowerCase()
  if (!search) return true
  return [tool.name, tool.server, tool.description, tool.effect, tool.status]
    .join(" ")
    .toLowerCase()
    .includes(search)
}

export function invocationMatches(row: ToolInvocation, state: ToolListState): boolean {
  const search = state.search.trim().toLowerCase()
  if (!search) return true
  return [row.tool, row.actor, row.result, row.id].join(" ").toLowerCase().includes(search)
}

export function sortTools(rows: Tool[], key: ToolSortKey, direction: ToolSortDirection): Tool[] {
  const multiplier = direction === "asc" ? 1 : -1
  const effectOrder: Record<ToolEffect, number> = { "read-only": 0, external: 1, mutating: 2 }
  const statusOrder: Record<ToolStatus, number> = { enabled: 0, disabled: 1 }
  return [...rows].sort((left, right) => {
    if (key === "effect") return multiplier * (effectOrder[left.effect] - effectOrder[right.effect])
    if (key === "status") return multiplier * (statusOrder[left.status] - statusOrder[right.status])
    return multiplier * left.name.localeCompare(right.name)
  })
}

export function toolSummary() {
  const readOnly = tools.filter((tool) => tool.effect === "read-only").length
  return {
    total: tools.length,
    readOnly,
    stateChanging: tools.length - readOnly,
    stepUp: tools.filter((tool) => tool.approval === "step-up").length,
    disabled: tools.filter((tool) => tool.status === "disabled").length,
    servers: [...new Set(tools.map((tool) => tool.server))].length,
  }
}

/** JSON Schema shown in the drawer, built from the fixture's parameter list. */
export function toolSchema(tool: Tool): string {
  const properties: Record<string, unknown> = {}
  for (const param of tool.params) {
    const property: Record<string, unknown> = { type: param.type }
    if (param.note) property.description = param.note
    properties[param.name] = property
  }
  return JSON.stringify(
    {
      type: "object",
      required: tool.params.filter((param) => param.required).map((param) => param.name),
      properties,
      additionalProperties: false,
    },
    null,
    2,
  )
}

export function emptyToolListState(): ToolListState {
  return {
    search: "",
    tab: "tools",
    effects: [],
    statuses: [],
    sort: "name",
    direction: "asc",
    tool: "",
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

export function parseToolQuery(query: Record<string, unknown>): ToolListState {
  const state = emptyToolListState()
  state.search = firstValue(query.q).trim().slice(0, 120)
  const tab = firstValue(query.tab)
  if (allowed(tab, ["tools", "invocations", "permissions"] as const)) state.tab = tab
  state.effects = [...new Set(listValues(query.effect).filter((entry) => allowed(entry, TOOL_EFFECTS)))]
  state.statuses = [...new Set(listValues(query.status).filter((entry) => allowed(entry, TOOL_STATUSES)))]
  const sort = firstValue(query.sort)
  if (allowed(sort, TOOL_SORT_KEYS)) state.sort = sort
  const direction = firstValue(query.dir)
  state.direction = direction === "asc" || direction === "desc" ? direction : TOOL_DEFAULT_SORT_DIRECTION[state.sort]
  const tool = firstValue(query.tool)
  state.tool = tool && toolByName(tool) ? tool : ""
  return state
}

export function serializeToolQuery(state: ToolListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.search.trim()) query.set("q", state.search.trim().slice(0, 120))
  if (state.tab !== "tools") query.set("tab", state.tab)
  if (state.effects.length) query.set("effect", state.effects.join(","))
  if (state.statuses.length) query.set("status", state.statuses.join(","))
  if (state.sort !== "name") query.set("sort", state.sort)
  if (state.direction !== TOOL_DEFAULT_SORT_DIRECTION[state.sort]) query.set("dir", state.direction)
  if (state.tool) query.set("tool", state.tool)
  return query
}

export function toolHref(state: ToolListState, toolName?: string): string {
  const next = { ...state, tool: toolName ?? state.tool }
  const query = serializeToolQuery(next).toString()
  return query ? `/mcp-tools?${query}` : "/mcp-tools"
}
