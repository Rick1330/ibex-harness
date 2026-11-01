/**
 * Shared live Agents query codec for operator.agents.v1.
 *
 * Keep the allowlisted fields aligned with services/api AgentListQuery:
 * cursor, limit, status, tags, search.
 */

export type LiveAgentStatus = "active" | "paused" | "suspended" | "archived"

export type LiveAgentQuery = {
  search: string | null
  status: LiveAgentStatus | null
  tags: string[]
  cursor: string | null
  limit: number
}

type QueryParams = URLSearchParams | Record<string, unknown>

const ALLOWED = new Set(["search", "status", "tags", "cursor", "limit"])
const STATUSES = new Set<LiveAgentStatus>(["active", "paused", "suspended", "archived"])
const MAX_TAGS = 32
const MAX_TAG_LENGTH = 64
const DEFAULT_LIMIT = 50

export class LiveAgentQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveAgentQueryError"
  }
}

function paramGet(params: QueryParams, key: string): string | null {
  if (params instanceof URLSearchParams) return params.get(key)
  const raw = params[key]
  if (Array.isArray(raw)) return typeof raw[0] === "string" ? raw[0] : null
  return typeof raw === "string" ? raw : null
}

function assertAllowedKeys(params: QueryParams): void {
  const keys = params instanceof URLSearchParams ? params.keys() : Object.keys(params)
  for (const key of keys) {
    if (!ALLOWED.has(key)) throw new LiveAgentQueryError(`Unknown query field: ${key}`)
  }
}

function boundedString(value: string | null, max: number, label: string): string | null {
  if (value == null || value === "") return null
  if (value.length > max) throw new LiveAgentQueryError(`${label} exceeds maximum length`)
  return value
}

function parseSearch(raw: string | null): string | null {
  const value = boundedString(raw, 200, "search")?.trim()
  return value ? value : null
}

function parseStatus(raw: string | null): LiveAgentStatus | null {
  if (raw == null || raw === "") return null
  if (STATUSES.has(raw as LiveAgentStatus)) return raw as LiveAgentStatus
  throw new LiveAgentQueryError("status must be active, paused, suspended, or archived")
}

function parseTags(raw: string | null): string[] {
  if (raw == null || raw === "") return []
  const tags = raw
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean)
  if (tags.length > MAX_TAGS) throw new LiveAgentQueryError("too many tags")
  for (const tag of tags) {
    if (tag.length > MAX_TAG_LENGTH) throw new LiveAgentQueryError("tag exceeds maximum length")
  }
  return [...new Set(tags)]
}

function parseCursor(raw: string | null): string | null {
  const cursor = boundedString(raw, 2048, "cursor")
  if (cursor && /\s/.test(cursor)) throw new LiveAgentQueryError("invalid cursor")
  return cursor
}

function parseLimit(raw: string | null): number {
  if (raw == null || raw === "") return DEFAULT_LIMIT
  const limit = Number(raw)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new LiveAgentQueryError("limit must be an integer between 1 and 100")
  }
  return limit
}

export function defaultLiveAgentQuery(): LiveAgentQuery {
  return { search: null, status: null, tags: [], cursor: null, limit: DEFAULT_LIMIT }
}

export function parseLiveAgentQuery(params: QueryParams): LiveAgentQuery {
  assertAllowedKeys(params)
  return {
    search: parseSearch(paramGet(params, "search")),
    status: parseStatus(paramGet(params, "status")),
    tags: parseTags(paramGet(params, "tags")),
    cursor: parseCursor(paramGet(params, "cursor")),
    limit: parseLimit(paramGet(params, "limit")),
  }
}

function baseParams(query: LiveAgentQuery): URLSearchParams {
  const params = new URLSearchParams()
  params.set("limit", String(query.limit))
  if (query.search) params.set("search", query.search)
  if (query.status) params.set("status", query.status)
  if (query.cursor) params.set("cursor", query.cursor)
  return params
}

/** API form: repeated `tags` parameters, as FastAPI expects for a list. */
export function serializeLiveAgentQuery(query: LiveAgentQuery): URLSearchParams {
  const params = baseParams(query)
  for (const tag of query.tags) params.append("tags", tag)
  return params
}

/** Browser form: one comma-separated `tags` parameter for a readable URL. */
export function serializeLiveAgentUrlQuery(query: LiveAgentQuery): URLSearchParams {
  const params = baseParams(query)
  if (query.tags.length > 0) params.set("tags", query.tags.join(","))
  return params
}

export function agentQueryKey(query: LiveAgentQuery): string {
  return serializeLiveAgentQuery(query).toString()
}
