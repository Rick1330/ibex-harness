import type { AgentEnv, AgentHealthState, AgentStatus } from "./agent-preview"

export const AGENT_STATUSES = ["active", "paused", "draining", "suspended", "archived"] as const
export const AGENT_ENVS = ["production", "staging", "dev"] as const
export const AGENT_HEALTH_STATES = [
  "failing",
  "attention",
  "healthy",
  "paused",
  "archived",
  "no_data",
] as const
export const AGENT_VIEWS = ["all", "attention", "budget", "drifted", "paused"] as const
export const AGENT_SORT_KEYS = [
  "health",
  "name",
  "owner",
  "runs",
  "errors",
  "p95",
  "budget",
  "coverage",
  "lastRun",
] as const
export const AGENT_GROUP_KEYS = ["none", "owner", "env", "health"] as const
export const AGENT_DENSITIES = ["comfortable", "compact"] as const

export type AgentView = (typeof AGENT_VIEWS)[number]
export type AgentSortKey = (typeof AGENT_SORT_KEYS)[number]
export type AgentSortDirection = "asc" | "desc"
export type AgentGroupKey = (typeof AGENT_GROUP_KEYS)[number]
export type AgentDensity = (typeof AGENT_DENSITIES)[number]

export type AgentListState = {
  search: string
  view: AgentView
  statuses: AgentStatus[]
  envs: AgentEnv[]
  models: string[]
  owners: string[]
  healths: AgentHealthState[]
  sort: AgentSortKey
  direction: AgentSortDirection
  group: AgentGroupKey
  density: AgentDensity
  includeNoData: boolean
}

export const AGENT_SORT_LABELS: Record<AgentSortKey, string> = {
  health: "Health",
  name: "Agent",
  owner: "Owner",
  runs: "Runs",
  errors: "Error rate",
  p95: "p95",
  budget: "Budget headroom",
  coverage: "Trace coverage",
  lastRun: "Last run",
}

export const AGENT_GROUP_LABELS: Record<AgentGroupKey, string> = {
  none: "None",
  owner: "Owner",
  env: "Environment",
  health: "Health",
}

export const AGENT_VIEW_LABELS: Record<AgentView, string> = {
  all: "All",
  attention: "Needs attention",
  budget: "Near budget",
  drifted: "Drifted",
  paused: "Paused",
}

export const AGENT_DEFAULT_SORT_DIRECTION: Record<AgentSortKey, AgentSortDirection> = {
  health: "asc",
  name: "asc",
  owner: "asc",
  runs: "desc",
  errors: "desc",
  p95: "desc",
  budget: "asc",
  coverage: "asc",
  lastRun: "desc",
}

export function emptyAgentListState(): AgentListState {
  return {
    search: "",
    view: "all",
    statuses: [],
    envs: [],
    models: [],
    owners: [],
    healths: [],
    sort: "health",
    direction: "asc",
    group: "none",
    density: "comfortable",
    includeNoData: false,
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
    .slice(0, 30)
}

function allowed<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

function allowedList<T extends string>(value: unknown, options: readonly T[]): T[] {
  return [...new Set(listValues(value).filter((entry): entry is T => allowed(entry, options)))]
}

export function parseAgentListQuery(query: Record<string, unknown>): AgentListState {
  const state = emptyAgentListState()
  state.search = firstValue(query.q).trim().slice(0, 120)
  const view = firstValue(query.view)
  if (allowed(view, AGENT_VIEWS)) state.view = view
  state.statuses = allowedList<AgentStatus>(query.status, AGENT_STATUSES)
  state.envs = allowedList<AgentEnv>(query.env, AGENT_ENVS)
  state.models = [...new Set(listValues(query.model))].slice(0, 12)
  state.owners = [...new Set(listValues(query.owner))].slice(0, 12)
  state.healths = allowedList<AgentHealthState>(query.health, AGENT_HEALTH_STATES)
  if (firstValue(query.attention) === "1") state.view = "attention"
  const sort = firstValue(query.sort)
  if (allowed(sort, AGENT_SORT_KEYS)) state.sort = sort
  const direction = firstValue(query.dir)
  if (direction === "asc" || direction === "desc") state.direction = direction
  else state.direction = AGENT_DEFAULT_SORT_DIRECTION[state.sort]
  const group = firstValue(query.group)
  if (allowed(group, AGENT_GROUP_KEYS)) state.group = group
  const density = firstValue(query.density)
  if (allowed(density, AGENT_DENSITIES)) state.density = density
  state.includeNoData = firstValue(query.all) === "1"
  return state
}

export function serializeAgentListQuery(state: AgentListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.search.trim()) query.set("q", state.search.trim().slice(0, 120))
  if (state.view !== "all") query.set("view", state.view)
  if (state.statuses.length) query.set("status", state.statuses.join(","))
  if (state.envs.length) query.set("env", state.envs.join(","))
  if (state.models.length) query.set("model", state.models.join(","))
  if (state.owners.length) query.set("owner", state.owners.join(","))
  if (state.healths.length) query.set("health", state.healths.join(","))
  if (state.sort !== "health") query.set("sort", state.sort)
  if (state.direction !== AGENT_DEFAULT_SORT_DIRECTION[state.sort]) query.set("dir", state.direction)
  if (state.group !== "none") query.set("group", state.group)
  if (state.density !== "comfortable") query.set("density", state.density)
  if (state.includeNoData) query.set("all", "1")
  return query
}

export function agentListHref(state: AgentListState): string {
  const query = serializeAgentListQuery(state).toString()
  return query ? `/agents?${query}` : "/agents"
}

export function agentDetailHref(agentId: string, returnTo: string, tab?: string): string {
  const params = new URLSearchParams()
  if (returnTo) params.set("return", returnTo)
  if (tab) params.set("tab", tab)
  const query = params.toString()
  return `/agents/${encodeURIComponent(agentId)}${query ? `?${query}` : ""}`
}
