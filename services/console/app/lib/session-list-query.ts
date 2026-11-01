import type { PreviewSession } from "./session-preview"

export const SESSION_VIEWS = ["all", "support", "security"] as const
export const SESSION_SORT_KEYS = ["activity", "turns", "duration", "cost"] as const
export const SESSION_DURATION_BANDS = ["short", "medium", "long"] as const
export const SESSION_ENVIRONMENTS = ["production", "staging", "development"] as const
export const SESSION_OUTCOMES = ["succeeded", "denied", "error"] as const
export const SESSION_TIERS = ["T1", "T2", "T3"] as const
export const SESSION_HIDEABLE_COLUMNS = ["id", "turns", "coverage", "cost"] as const

export type SessionView = (typeof SESSION_VIEWS)[number]
export type SessionSortKey = (typeof SESSION_SORT_KEYS)[number]
export type SessionSortDirection = "asc" | "desc"
export type SessionDurationBand = (typeof SESSION_DURATION_BANDS)[number]
export type SessionEnvironment = (typeof SESSION_ENVIRONMENTS)[number]
export type SessionOutcome = (typeof SESSION_OUTCOMES)[number]
export type SessionTier = (typeof SESSION_TIERS)[number]
export type SessionHideableColumn = (typeof SESSION_HIDEABLE_COLUMNS)[number]

export type SessionListState = {
  search: string
  view: SessionView
  environments: SessionEnvironment[]
  outcomes: SessionOutcome[]
  tier: SessionTier | ""
  agent: string
  id: string
  duration: SessionDurationBand | ""
  hidden: SessionHideableColumn[]
  sort: SessionSortKey
  direction: SessionSortDirection
}

export const SESSION_DURATION_LABELS: Record<SessionDurationBand, string> = {
  short: "Under 20s",
  medium: "20s – 30s",
  long: "Over 30s",
}

export const SESSION_VIEW_LABELS: Record<SessionView, string> = {
  all: "All sessions",
  support: "Support triage",
  security: "Denied only",
}

export const SESSION_SORT_LABELS: Record<SessionSortKey, string> = {
  activity: "Last activity",
  turns: "Turns",
  duration: "Duration",
  cost: "Cost",
}

export function emptySessionListState(): SessionListState {
  return {
    search: "",
    view: "all",
    environments: [],
    outcomes: [],
    tier: "",
    agent: "",
    id: "",
    duration: "",
    hidden: [],
    sort: "activity",
    direction: "desc",
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
    .slice(0, 20)
}

function allowed<T extends string>(value: string, options: readonly T[]): value is T {
  return (options as readonly string[]).includes(value)
}

function allowedList<T extends string>(value: unknown, options: readonly T[]): T[] {
  return [...new Set(listValues(value).filter((entry): entry is T => allowed(entry, options)))]
}

export function parseSessionListQuery(query: Record<string, unknown>): SessionListState {
  const state = emptySessionListState()
  state.search = firstValue(query.q).trim().slice(0, 200)
  const view = firstValue(query.view)
  if (allowed(view, SESSION_VIEWS)) state.view = view
  state.environments = allowedList<SessionEnvironment>(query.env, SESSION_ENVIRONMENTS)
  state.outcomes = allowedList<SessionOutcome>(query.outcome, SESSION_OUTCOMES)
  const tier = firstValue(query.tier)
  if (allowed(tier, SESSION_TIERS)) state.tier = tier
  state.agent = firstValue(query.agent).slice(0, 120)
  state.id = firstValue(query.id).slice(0, 64)
  const duration = firstValue(query.duration)
  if (allowed(duration, SESSION_DURATION_BANDS)) state.duration = duration
  state.hidden = allowedList<SessionHideableColumn>(query.hide, SESSION_HIDEABLE_COLUMNS)
  const sort = firstValue(query.sort)
  if (allowed(sort, SESSION_SORT_KEYS)) state.sort = sort
  const direction = firstValue(query.dir)
  if (direction === "asc" || direction === "desc") state.direction = direction
  return state
}

export function serializeSessionListQuery(state: SessionListState): URLSearchParams {
  const query = new URLSearchParams()
  if (state.search.trim()) query.set("q", state.search.trim().slice(0, 200))
  if (state.view !== "all") query.set("view", state.view)
  if (state.environments.length) query.set("env", state.environments.join(","))
  if (state.outcomes.length) query.set("outcome", state.outcomes.join(","))
  if (state.tier) query.set("tier", state.tier)
  if (state.agent) query.set("agent", state.agent.slice(0, 120))
  if (state.id) query.set("id", state.id.slice(0, 64))
  if (state.duration) query.set("duration", state.duration)
  if (state.hidden.length) query.set("hide", state.hidden.join(","))
  if (state.sort !== "activity") query.set("sort", state.sort)
  if (state.direction !== "desc") query.set("dir", state.direction)
  return query
}

export function sessionListHref(state: SessionListState): string {
  const query = serializeSessionListQuery(state).toString()
  return query ? `/sessions?${query}` : "/sessions"
}

export function parseDurationSeconds(value: string): number {
  const minutes = value.match(/(\d+)\s*m/)
  const seconds = value.match(/([\d.]+)\s*s/)
  if (minutes) return Number(minutes[1]) * 60 + Number.parseFloat(seconds?.[1] ?? "0")
  return Number.parseFloat(value) || 0
}

export function matchesDurationBand(seconds: number, band: SessionDurationBand): boolean {
  if (band === "short") return seconds < 20
  if (band === "medium") return seconds >= 20 && seconds <= 30
  return seconds > 30
}

export function filterSessions(sessions: PreviewSession[], state: SessionListState): PreviewSession[] {
  const query = state.search.trim().toLowerCase()
  const idQuery = state.id.trim().toLowerCase()

  return sessions.filter((session) => {
    if (state.view === "support" && session.agent !== "Support triage") return false
    if (state.view === "security" && session.outcome !== "denied") return false
    if (state.environments.length > 0 && !state.environments.includes(session.env)) return false
    if (state.outcomes.length > 0 && !state.outcomes.includes(session.outcome)) return false
    if (state.tier && session.tier !== state.tier) return false
    if (state.agent && session.agent !== state.agent) return false
    if (idQuery && !session.id.toLowerCase().includes(idQuery)) return false
    if (state.duration && !matchesDurationBand(parseDurationSeconds(session.duration), state.duration)) return false
    if (!query) return true

    return [session.id, session.title, session.agent, session.env, session.outcome, session.error, session.tier]
      .some((value) => value.toLowerCase().includes(query))
  })
}

function activitySeconds(value: string): number {
  const [hours = "0", minutes = "0", seconds = "0"] = value.split(":")
  return Number(hours) * 3600 + Number(minutes) * 60 + Number(seconds)
}

function costValue(value: string): number {
  return Number.parseFloat(value.replace(/[^0-9.]/g, "")) || 0
}

export function sortSessions(
  sessions: PreviewSession[],
  sort: SessionSortKey,
  direction: SessionSortDirection,
): PreviewSession[] {
  const sorted = [...sessions].sort((first, second) => {
    let result: number
    if (sort === "activity") result = activitySeconds(first.last) - activitySeconds(second.last)
    else if (sort === "turns") result = first.turns - second.turns
    else if (sort === "duration") result = parseDurationSeconds(first.duration) - parseDurationSeconds(second.duration)
    else result = costValue(first.cost) - costValue(second.cost)
    return result === 0 ? first.id.localeCompare(second.id) : result
  })
  return direction === "asc" ? sorted : sorted.reverse()
}

export function activeSessionFilterCount(state: SessionListState): number {
  return (
    state.environments.length +
    state.outcomes.length +
    (state.tier ? 1 : 0) +
    (state.agent ? 1 : 0) +
    (state.id ? 1 : 0) +
    (state.duration ? 1 : 0) +
    (state.view !== "all" ? 1 : 0)
  )
}

export function hasSessionFilters(state: SessionListState): boolean {
  return state.search.trim().length > 0 || activeSessionFilterCount(state) > 0
}
