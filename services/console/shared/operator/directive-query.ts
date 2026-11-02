/**
 * Shared live Directives query codecs for `operator.directives.versions.v1`.
 *
 * The list is a keyset page over `(updated_at, id)`; the detail is a version
 * timeline plus per-version usage in a window. Neither carries instruction text.
 */

import type { DirectiveUsageRange } from "./contracts"

export const DIRECTIVE_STATES = ["all", "active", "inactive"] as const
export type DirectiveStateFilter = (typeof DIRECTIVE_STATES)[number]

export type LiveDirectiveListQuery = {
  state: DirectiveStateFilter
  agentId: string | null
  cursor: string | null
  limit: number
}

export type LiveDirectiveDetailQuery = {
  range: DirectiveUsageRange
}

type QueryParams = URLSearchParams | Record<string, unknown>

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const LIST_ALLOWED = new Set(["state", "agent_id", "cursor", "limit"])
const DETAIL_ALLOWED = new Set(["range"])
const USAGE_RANGES = new Set<string>(["24h", "7d", "30d"])
const DEFAULT_LIMIT = 50

export class LiveDirectiveQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveDirectiveQueryError"
  }
}

function paramGet(params: QueryParams, key: string): string | null {
  if (params instanceof URLSearchParams) return params.get(key)
  const raw = params[key]
  if (Array.isArray(raw)) return typeof raw[0] === "string" ? raw[0] : null
  return typeof raw === "string" ? raw : null
}

function assertAllowed(params: QueryParams, allowed: Set<string>): void {
  const keys = params instanceof URLSearchParams ? [...params.keys()] : Object.keys(params)
  for (const key of keys) {
    if (!allowed.has(key)) throw new LiveDirectiveQueryError(`Unknown query field: ${key}`)
  }
}

function parseState(raw: string | null): DirectiveStateFilter {
  if (raw == null || raw === "") return "all"
  if ((DIRECTIVE_STATES as readonly string[]).includes(raw)) return raw as DirectiveStateFilter
  throw new LiveDirectiveQueryError("state must be all, active, or inactive")
}

function parseAgentId(raw: string | null): string | null {
  if (raw == null || raw === "") return null
  if (!UUID_RE.test(raw)) throw new LiveDirectiveQueryError("agent_id must be a UUID")
  return raw.toLowerCase()
}

function parseCursor(raw: string | null): string | null {
  if (raw == null || raw === "") return null
  if (raw.length > 2048 || /\s/.test(raw)) throw new LiveDirectiveQueryError("invalid cursor")
  return raw
}

function parseLimit(raw: string | null): number {
  if (raw == null || raw === "") return DEFAULT_LIMIT
  const limit = Number(raw)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new LiveDirectiveQueryError("limit must be an integer between 1 and 100")
  }
  return limit
}

function parseUsageRange(raw: string | null): DirectiveUsageRange {
  if (raw == null || raw === "") return "7d"
  if (USAGE_RANGES.has(raw)) return raw as DirectiveUsageRange
  throw new LiveDirectiveQueryError("range must be one of 24h, 7d, 30d")
}

export function defaultLiveDirectiveListQuery(): LiveDirectiveListQuery {
  return { state: "all", agentId: null, cursor: null, limit: DEFAULT_LIMIT }
}

export function defaultLiveDirectiveDetailQuery(): LiveDirectiveDetailQuery {
  return { range: "7d" }
}

export function parseLiveDirectiveListQuery(params: QueryParams): LiveDirectiveListQuery {
  assertAllowed(params, LIST_ALLOWED)
  return {
    state: parseState(paramGet(params, "state")),
    agentId: parseAgentId(paramGet(params, "agent_id")),
    cursor: parseCursor(paramGet(params, "cursor")),
    limit: parseLimit(paramGet(params, "limit")),
  }
}

export function parseLiveDirectiveDetailQuery(params: QueryParams): LiveDirectiveDetailQuery {
  assertAllowed(params, DETAIL_ALLOWED)
  return { range: parseUsageRange(paramGet(params, "range")) }
}

/** Keep the fields that parse and drop the rest, so the URL can be rewritten to match. */
export function parseLiveDirectiveListQueryLenient(params: QueryParams): LiveDirectiveListQuery {
  const field = <T>(read: () => T, fallback: T): T => {
    try {
      return read()
    } catch {
      return fallback
    }
  }
  const defaults = defaultLiveDirectiveListQuery()
  return {
    state: field(() => parseState(paramGet(params, "state")), defaults.state),
    agentId: field(() => parseAgentId(paramGet(params, "agent_id")), defaults.agentId),
    cursor: field(() => parseCursor(paramGet(params, "cursor")), defaults.cursor),
    limit: field(() => parseLimit(paramGet(params, "limit")), defaults.limit),
  }
}

export function parseLiveDirectiveDetailQueryLenient(
  params: QueryParams,
): LiveDirectiveDetailQuery {
  const field = <T>(read: () => T, fallback: T): T => {
    try {
      return read()
    } catch {
      return fallback
    }
  }
  return { range: field(() => parseUsageRange(paramGet(params, "range")), "7d") }
}

export function serializeLiveDirectiveListQuery(query: LiveDirectiveListQuery): URLSearchParams {
  const params = new URLSearchParams()
  params.set("limit", String(query.limit))
  if (query.state !== "all") params.set("state", query.state)
  if (query.agentId) params.set("agent_id", query.agentId)
  if (query.cursor) params.set("cursor", query.cursor)
  return params
}

export function serializeLiveDirectiveDetailQuery(query: LiveDirectiveDetailQuery): URLSearchParams {
  return new URLSearchParams({ range: query.range })
}

export function liveDirectiveListKey(query: LiveDirectiveListQuery): string {
  return serializeLiveDirectiveListQuery(query).toString()
}
