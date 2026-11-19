import { formatGovernNumber } from "./govern-format"
import type { OperatorAgent, OperatorSessionRecord, SessionStatus } from "~~/shared/operator/contracts"

/**
 * View model for the Sessions index and the session detail record.
 *
 * `operator.sessions.v1` is metadata-only: it carries no message content, no
 * session title, no cost, no environment and no outcome error code. Every value
 * here is therefore read from a field the contract actually returns, and a
 * value that has no field stays absent rather than being estimated. The one
 * value that needs a second read is the agent name: it is joined from the
 * agents projection, and an agent outside that read falls back to the id the
 * session itself carries.
 */

const SHORT_ID_HEAD = 8
const SHORT_ID_TAIL = 4

export const SESSION_STATUS_ORDER: SessionStatus[] = ["active", "completed", "abandoned", "error"]

export const SESSION_STATUS_LABELS: Record<SessionStatus, string> = {
  active: "Active",
  completed: "Completed",
  abandoned: "Abandoned",
  error: "Error",
}

/** Display in the agent cell when the joined agent read does not carry the id. */
export const AGENT_NOT_JOINED_NOTE = "Name not in this agent page"

/** Display in the agent cell when the agents read itself did not return. */
export const AGENT_READ_FAILED_NOTE = "Agent read unavailable"

export type SessionAgentLabel = {
  id: string
  name: string | null
  slug: string | null
}

export type SessionListRow = {
  id: string
  shortId: string
  /** `external_id` and `model` on one line: whatever identifies this session to a reader. */
  meta: string
  externalId: string | null
  status: SessionStatus
  agentId: string
  agentName: string | null
  agentSlug: string | null
  model: string
  provider: string
  turnsLabel: string
  tokensLabel: string
  latencyMs: number
  latencyLabel: string
  coverageLabel: string
  coveragePercent: number | null
  coverageNote: string
  activityAt: string
  /** `completed_at` is when the session reached a terminal state, so it reads "Ended". */
  activityKind: "Ended" | "Updated"
  createdAt: string
}

export type SessionSegment = {
  id: "all" | SessionStatus
  label: string
  count: number
}

export type SessionDurationBucket = "under-1s" | "1s-to-10s" | "over-10s"

export type SessionPageFilters = {
  search: string
  model: string | null
  provider: string | null
  duration: SessionDurationBucket | null
}

export type SessionColumnId = "coverage" | "tokens"

export type SessionFilterOption = { value: string; label: string }

export const SESSION_OPTIONAL_COLUMNS: { id: SessionColumnId; label: string }[] = [
  { id: "coverage", label: "Coverage" },
  { id: "tokens", label: "Tokens" },
]

export const DEFAULT_SESSION_COLUMNS: SessionColumnId[] = ["coverage"]

export const DEFAULT_SESSION_PAGE_FILTERS: SessionPageFilters = {
  search: "",
  model: null,
  provider: null,
  duration: null,
}

export const SESSION_DURATION_OPTIONS: { value: SessionDurationBucket; label: string }[] = [
  { value: "under-1s", label: "Under 1 s" },
  { value: "1s-to-10s", label: "1–10 s" },
  { value: "over-10s", label: "10 s or more" },
]

const DURATION_BOUNDS: Record<SessionDurationBucket, (ms: number) => boolean> = {
  "under-1s": (ms) => ms < 1_000,
  "1s-to-10s": (ms) => ms >= 1_000 && ms < 10_000,
  "over-10s": (ms) => ms >= 10_000,
}

/** `88888888-8888-4888-8888-888888888888` → `88888888…8888`. Never shortens a short value. */
export function shortId(value: string): string {
  if (value.length <= SHORT_ID_HEAD + SHORT_ID_TAIL + 1) return value
  return `${value.slice(0, SHORT_ID_HEAD)}…${value.slice(-SHORT_ID_TAIL)}`
}

/**
 * `total_latency_ms` is the sum of the recorded turn latencies, not wall-clock
 * duration, so it is labelled as a latency everywhere it appears.
 */
export function formatSessionLatency(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "Not recorded"
  if (ms < 1_000) return `${formatGovernNumber(Math.round(ms))} ms`
  const seconds = ms / 1_000
  if (seconds < 59.95) return `${seconds.toFixed(1)} s`
  const totalSeconds = Math.round(seconds)
  return `${Math.floor(totalSeconds / 60)}m ${String(totalSeconds % 60).padStart(2, "0")}s`
}

/**
 * Extraction progress as the contract states it: `last_extracted_turn` over
 * `turn_count`. The numerator is never inflated (no `+1` for a 0-based index),
 * because the field is the only evidence of how far extraction has progressed.
 */
export function sessionCoverage(extracted: number, turns: number): { label: string; percent: number | null } {
  const label = `${formatGovernNumber(extracted)} / ${formatGovernNumber(turns)}`
  if (turns <= 0) return { label, percent: null }
  return { label, percent: Math.min(100, Math.round((extracted / turns) * 100)) }
}

function coverageNote(percent: number | null): string {
  return percent === null ? "No turns recorded" : `${percent}% extracted`
}

function agentLabels(agents: OperatorAgent[]): Map<string, SessionAgentLabel> {
  const index = new Map<string, SessionAgentLabel>()
  for (const agent of agents) index.set(agent.id, { id: agent.id, name: agent.name, slug: agent.slug })
  return index
}

function sessionMeta(externalId: string | null, model: string): string {
  return externalId === null ? model : `${externalId} · ${model}`
}

export function toSessionListRow(
  session: OperatorSessionRecord,
  agent: SessionAgentLabel | undefined,
): SessionListRow {
  const coverage = sessionCoverage(session.last_extracted_turn, session.turn_count)
  const completed = session.completed_at !== null
  return {
    id: session.id,
    shortId: shortId(session.id),
    meta: sessionMeta(session.external_id, session.model),
    externalId: session.external_id,
    status: session.status,
    agentId: session.agent_id,
    agentName: agent?.name ?? null,
    agentSlug: agent?.slug ?? null,
    model: session.model,
    provider: session.provider,
    turnsLabel: formatGovernNumber(session.turn_count),
    tokensLabel: `${formatGovernNumber(session.total_input_tokens)} / ${formatGovernNumber(session.total_output_tokens)}`,
    latencyMs: session.total_latency_ms,
    latencyLabel: formatSessionLatency(session.total_latency_ms),
    coverageLabel: coverage.label,
    coveragePercent: coverage.percent,
    coverageNote: coverageNote(coverage.percent),
    activityAt: completed ? (session.completed_at as string) : session.updated_at,
    activityKind: completed ? "Ended" : "Updated",
    createdAt: session.created_at,
  }
}

/**
 * Join the session page against the agents page.
 *
 * The API has no "agents by id" query, so the join is bounded by whatever the
 * agents read returned. A session whose `agent_id` is outside that read keeps
 * its real id and reports no name — it is never blank, and no name is invented.
 */
export function toSessionListRows(
  sessions: OperatorSessionRecord[],
  agents: OperatorAgent[],
): SessionListRow[] {
  const index = agentLabels(agents)
  return sessions.map((session) => toSessionListRow(session, index.get(session.agent_id)))
}

/** The second line of the Agent cell: the slug, or why the name is missing. */
export function agentSecondaryLabel(row: SessionListRow, readFailed: boolean): string {
  if (row.agentSlug) return row.agentSlug
  return readFailed ? AGENT_READ_FAILED_NOTE : AGENT_NOT_JOINED_NOTE
}

export function matchesSessionSearch(row: SessionListRow, query: string): boolean {
  const needle = query.trim().toLowerCase()
  if (!needle) return true
  if (row.id.toLowerCase().includes(needle)) return true
  return row.externalId !== null && row.externalId.toLowerCase().includes(needle)
}

function matchesDuration(row: SessionListRow, bucket: SessionDurationBucket | null): boolean {
  if (bucket === null) return true
  return DURATION_BOUNDS[bucket](row.latencyMs)
}

/** The page-scoped filters. Outcome and agent are the API's own query fields. */
export function filterSessionRows(rows: SessionListRow[], filters: SessionPageFilters): SessionListRow[] {
  return rows
    .filter((row) => matchesSessionSearch(row, filters.search))
    .filter((row) => filters.model === null || row.model === filters.model)
    .filter((row) => filters.provider === null || row.provider === filters.provider)
    .filter((row) => matchesDuration(row, filters.duration))
}

/** The filters in force: the two the API applies, plus the page-scoped ones. */
export function activeSessionFilterCount(
  filters: SessionPageFilters,
  scope: { status: SessionStatus | null; agentId: string | null },
): number {
  const requestScoped = [scope.status !== null, scope.agentId !== null].filter(Boolean).length
  return sessionPageFilterCount(filters) + requestScoped
}

export function sessionPageFilterCount(filters: SessionPageFilters): number {
  return [filters.search.trim() !== "", filters.model !== null, filters.provider !== null, filters.duration !== null]
    .filter(Boolean)
    .length
}

/**
 * Tabs describe the rows that were actually loaded, so a segment exists only
 * when its status occurs. Counts are per page: the API returns no organization
 * total, and the tab badge must not imply one.
 */
export function sessionSegments(rows: SessionListRow[]): SessionSegment[] {
  const counts = new Map<SessionStatus, number>()
  for (const row of rows) counts.set(row.status, (counts.get(row.status) ?? 0) + 1)
  const segments: SessionSegment[] = [{ id: "all", label: "All sessions", count: rows.length }]
  for (const status of SESSION_STATUS_ORDER) {
    const count = counts.get(status) ?? 0
    if (count > 0) segments.push({ id: status, label: SESSION_STATUS_LABELS[status], count })
  }
  return segments
}

export function segmentSessionRows(rows: SessionListRow[], segment: SessionSegment["id"]): SessionListRow[] {
  if (segment === "all") return rows
  return rows.filter((row) => row.status === segment)
}

/** Distinct values that occur on the page, for a page-scoped facet select. */
export function sessionFacets(rows: SessionListRow[], key: "model" | "provider"): string[] {
  return [...new Set(rows.map((row) => row[key]))].sort((left, right) => left.localeCompare(right))
}

/**
 * Agent options for the server-side `agent_id` filter. A session link can name
 * an agent outside the loaded agents page; that id stays selectable and is
 * labelled as such instead of silently disappearing from the control.
 */
export function agentFilterOptions(agents: OperatorAgent[], selected: string | null): SessionFilterOption[] {
  const options = agents
    .map((agent) => ({ value: agent.id, label: `${agent.name} · ${agent.slug}` }))
    .sort((left, right) => left.label.localeCompare(right.label))
  if (!selected) return options
  if (options.some((option) => option.value === selected)) return options
  return [{ value: selected, label: `${shortId(selected)} · not in this agent page` }, ...options]
}

export function sessionColumnVisible(columns: SessionColumnId[], id: SessionColumnId): boolean {
  return columns.includes(id)
}

export function toggleSessionColumn(columns: SessionColumnId[], id: SessionColumnId): SessionColumnId[] {
  if (columns.includes(id)) return columns.filter((column) => column !== id)
  return [...SESSION_OPTIONAL_COLUMNS.map((column) => column.id)].filter(
    (column) => column === id || columns.includes(column),
  )
}
