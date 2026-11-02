/**
 * Shared live Sessions query codec for operator.sessions.v1.
 *
 * Keep the allowlisted fields aligned with the API query model:
 * agent_id, status, cursor, limit.
 */

import type { SessionStatus } from "./contracts"

export type LiveSessionQuery = {
  agentId: string | null
  status: SessionStatus | null
  cursor: string | null
  limit: number
}

type QueryParams = URLSearchParams | Record<string, unknown>

const ALLOWED = new Set(["agent_id", "status", "cursor", "limit"])
const STATUSES = new Set<SessionStatus>(["active", "completed", "abandoned", "error"])
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const DEFAULT_LIMIT = 50

export class LiveSessionQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveSessionQueryError"
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
    if (!ALLOWED.has(key)) throw new LiveSessionQueryError(`Unknown query field: ${key}`)
  }
}

function parseUuid(raw: string | null): string | null {
  if (raw == null || raw === "") return null
  if (!UUID_RE.test(raw)) throw new LiveSessionQueryError("agent_id must be a UUID")
  return raw.toLowerCase()
}

function parseStatus(raw: string | null): SessionStatus | null {
  if (raw == null || raw === "") return null
  if (STATUSES.has(raw as SessionStatus)) return raw as SessionStatus
  throw new LiveSessionQueryError("invalid session status")
}

function parseCursor(raw: string | null): string | null {
  if (raw == null || raw === "") return null
  if (raw.length > 2048 || /\s/.test(raw)) throw new LiveSessionQueryError("invalid cursor")
  return raw
}

function parseLimit(raw: string | null): number {
  if (raw == null || raw === "") return DEFAULT_LIMIT
  const limit = Number(raw)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new LiveSessionQueryError("limit must be an integer between 1 and 100")
  }
  return limit
}

export function defaultLiveSessionQuery(): LiveSessionQuery {
  return { agentId: null, status: null, cursor: null, limit: DEFAULT_LIMIT }
}

export function parseLiveSessionQuery(params: QueryParams): LiveSessionQuery {
  assertAllowedKeys(params)
  return {
    agentId: parseUuid(paramGet(params, "agent_id")),
    status: parseStatus(paramGet(params, "status")),
    cursor: parseCursor(paramGet(params, "cursor")),
    limit: parseLimit(paramGet(params, "limit")),
  }
}

export function serializeLiveSessionQuery(query: LiveSessionQuery): URLSearchParams {
  const params = new URLSearchParams()
  params.set("limit", String(query.limit))
  if (query.agentId) params.set("agent_id", query.agentId)
  if (query.status) params.set("status", query.status)
  if (query.cursor) params.set("cursor", query.cursor)
  return params
}

export function liveSessionQueryKey(query: LiveSessionQuery): string {
  return serializeLiveSessionQuery(query).toString()
}
