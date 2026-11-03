/**
 * Shared live Memories query codec for operator.memories.v1.
 *
 * Keep the allowlisted fields aligned with the API query model:
 * agent_id, session_id, status, category, cursor, limit.
 */

import type { MemoryCategory, MemoryStatus } from "./contracts"

export type LiveMemoryQuery = {
  agentId: string | null
  sessionId: string | null
  status: MemoryStatus | null
  category: MemoryCategory | null
  cursor: string | null
  limit: number
}

type QueryParams = URLSearchParams | Record<string, unknown>

const ALLOWED = new Set(["agent_id", "session_id", "status", "category", "cursor", "limit"])
const STATUSES = new Set<MemoryStatus>([
  "active",
  "superseded",
  "merged_into",
  "archived",
  "quarantined",
  "deleted",
])
const CATEGORIES = new Set<MemoryCategory>([
  "factual",
  "preference",
  "behavioral",
  "episodic",
  "procedural",
])
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const DEFAULT_LIMIT = 50

export class LiveMemoryQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveMemoryQueryError"
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
    if (!ALLOWED.has(key)) throw new LiveMemoryQueryError(`Unknown query field: ${key}`)
  }
}

function parseUuid(raw: string | null, label: string): string | null {
  if (raw == null || raw === "") return null
  if (!UUID_RE.test(raw)) throw new LiveMemoryQueryError(`${label} must be a UUID`)
  return raw.toLowerCase()
}

function parseStatus(raw: string | null): MemoryStatus | null {
  if (raw == null || raw === "") return null
  if (STATUSES.has(raw as MemoryStatus)) return raw as MemoryStatus
  throw new LiveMemoryQueryError("invalid memory status")
}

function parseCategory(raw: string | null): MemoryCategory | null {
  if (raw == null || raw === "") return null
  if (CATEGORIES.has(raw as MemoryCategory)) return raw as MemoryCategory
  throw new LiveMemoryQueryError("invalid memory category")
}

function parseCursor(raw: string | null): string | null {
  if (raw == null || raw === "") return null
  if (raw.length > 2048 || /\s/.test(raw)) throw new LiveMemoryQueryError("invalid cursor")
  return raw
}

function parseLimit(raw: string | null): number {
  if (raw == null || raw === "") return DEFAULT_LIMIT
  const limit = Number(raw)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new LiveMemoryQueryError("limit must be an integer between 1 and 100")
  }
  return limit
}

export function defaultLiveMemoryQuery(): LiveMemoryQuery {
  return { agentId: null, sessionId: null, status: null, category: null, cursor: null, limit: DEFAULT_LIMIT }
}

export function parseLiveMemoryQuery(params: QueryParams): LiveMemoryQuery {
  assertAllowedKeys(params)
  return {
    agentId: parseUuid(paramGet(params, "agent_id"), "agent_id"),
    sessionId: parseUuid(paramGet(params, "session_id"), "session_id"),
    status: parseStatus(paramGet(params, "status")),
    category: parseCategory(paramGet(params, "category")),
    cursor: parseCursor(paramGet(params, "cursor")),
    limit: parseLimit(paramGet(params, "limit")),
  }
}

/**
 * Best-effort parse for a URL the operator did not construct, such as a stale
 * bookmark or a hand-edited link. The strict parser throws on the first bad
 * field, which would force the page to fall back to an unfiltered first page
 * while the address bar still shows the filter. Keep every field that parses
 * and drop the rest, so the page can rewrite the URL to match what it actually
 * fetches instead of widening the list silently.
 */
export function parseLiveMemoryQueryLenient(params: QueryParams): LiveMemoryQuery {
  const field = <T>(read: () => T, fallback: T): T => {
    try {
      return read()
    } catch {
      return fallback
    }
  }
  const defaults = defaultLiveMemoryQuery()
  return {
    agentId: field(() => parseUuid(paramGet(params, "agent_id"), "agent_id"), defaults.agentId),
    sessionId: field(() => parseUuid(paramGet(params, "session_id"), "session_id"), defaults.sessionId),
    status: field(() => parseStatus(paramGet(params, "status")), defaults.status),
    category: field(() => parseCategory(paramGet(params, "category")), defaults.category),
    cursor: field(() => parseCursor(paramGet(params, "cursor")), defaults.cursor),
    limit: field(() => parseLimit(paramGet(params, "limit")), defaults.limit),
  }
}

export function serializeLiveMemoryQuery(query: LiveMemoryQuery): URLSearchParams {
  const params = new URLSearchParams()
  params.set("limit", String(query.limit))
  if (query.agentId) params.set("agent_id", query.agentId)
  if (query.sessionId) params.set("session_id", query.sessionId)
  if (query.status) params.set("status", query.status)
  if (query.category) params.set("category", query.category)
  if (query.cursor) params.set("cursor", query.cursor)
  return params
}

export function liveMemoryQueryKey(query: LiveMemoryQuery): string {
  return serializeLiveMemoryQuery(query).toString()
}
