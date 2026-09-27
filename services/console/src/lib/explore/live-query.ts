/**
 * Shared live Explore query codec for operator.trace-query.v1.
 * Keep allowlisted fields aligned with services/api OperatorTraceListQuery.
 */

export type LiveExploreQuery = {
  limit: number
  status: "ok" | "error" | null
  started_after: string | null
  started_before: string | null
  cursor: string | null
  trace_id: string | null
  request_id: string | null
  run_id: string | null
  session_id: string | null
  error_code: string | null
  completeness: string | null
  capture_mode: string | null
}

type QueryParams = URLSearchParams | Record<string, string | string[] | undefined>

const ALLOWED = new Set([
  "limit",
  "status",
  "started_after",
  "started_before",
  "cursor",
  "trace_id",
  "request_id",
  "run_id",
  "session_id",
  "error_code",
  "completeness",
  "capture_mode",
])

const COMPLETENESS = new Set([
  "complete",
  "partial",
  "sampled",
  "late",
  "redacted",
  "expired",
  "deleted",
  "simulated",
])

const OPTIONAL_STRING_FIELDS: ReadonlyArray<{
  key: keyof Omit<LiveExploreQuery, "limit" | "status" | "cursor" | "completeness">
  max: number
}> = [
  { key: "started_after", max: 64 },
  { key: "started_before", max: 64 },
  { key: "trace_id", max: 256 },
  { key: "request_id", max: 256 },
  { key: "run_id", max: 36 },
  { key: "session_id", max: 36 },
  { key: "error_code", max: 128 },
  { key: "capture_mode", max: 32 },
]

const SERIALIZE_FIELDS: ReadonlyArray<{
  key: Exclude<keyof LiveExploreQuery, "limit">
  omitWhenDropCursor?: boolean
}> = [
  { key: "status" },
  { key: "started_after" },
  { key: "started_before" },
  { key: "cursor", omitWhenDropCursor: true },
  { key: "trace_id" },
  { key: "request_id" },
  { key: "run_id" },
  { key: "session_id" },
  { key: "error_code" },
  { key: "completeness" },
  { key: "capture_mode" },
]

export class LiveExploreQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveExploreQueryError"
  }
}

function paramGet(params: QueryParams, key: string): string | null {
  if (params instanceof URLSearchParams) return params.get(key)
  const raw = params[key]
  if (Array.isArray(raw)) return raw[0] ?? null
  return raw ?? null
}

function assertAllowedKeys(params: QueryParams): void {
  const keys = params instanceof URLSearchParams ? params.keys() : Object.keys(params)
  for (const key of keys) {
    if (!ALLOWED.has(key)) throw new LiveExploreQueryError(`Unknown query field: ${key}`)
  }
}

function optionalBoundedString(value: string | null | undefined, max: number, label: string): string | null {
  if (value == null || value === "") return null
  if (value.length > max) throw new LiveExploreQueryError(`${label} exceeds maximum length`)
  return value
}

function limitOrDefault(raw: string | null): number | null {
  if (raw == null) return 50
  if (raw === "") return 50
  return null
}

function assertLimitInRange(limit: number): void {
  if (!Number.isInteger(limit)) {
    throw new LiveExploreQueryError("limit must be an integer between 1 and 100")
  }
  if (limit < 1) {
    throw new LiveExploreQueryError("limit must be an integer between 1 and 100")
  }
  if (limit > 100) {
    throw new LiveExploreQueryError("limit must be an integer between 1 and 100")
  }
}

function parseLimit(raw: string | null): number {
  const fallback = limitOrDefault(raw)
  if (fallback != null) return fallback
  const limit = Number(raw)
  assertLimitInRange(limit)
  return limit
}

function parseStatus(raw: string | null): LiveExploreQuery["status"] {
  if (raw === "ok" || raw === "error") return raw
  if (raw == null || raw === "") return null
  throw new LiveExploreQueryError("status must be ok or error")
}

function cursorHasIllegalWhitespace(cursor: string): boolean {
  if (cursor.includes(" ")) return true
  return cursor.includes("\n")
}

function parseCursor(raw: string | null): string | null {
  const cursor = optionalBoundedString(raw, 2048, "cursor")
  if (!cursor) return null
  if (cursorHasIllegalWhitespace(cursor)) {
    throw new LiveExploreQueryError("invalid cursor")
  }
  return cursor
}

function parseCompleteness(raw: string | null): string | null {
  const completeness = optionalBoundedString(raw, 32, "completeness")
  if (!completeness) return null
  if (!COMPLETENESS.has(completeness)) {
    throw new LiveExploreQueryError("invalid completeness")
  }
  return completeness
}

export function parseLiveExploreQuery(params: QueryParams): LiveExploreQuery {
  assertAllowedKeys(params)

  const query: LiveExploreQuery = {
    limit: parseLimit(paramGet(params, "limit")),
    status: parseStatus(paramGet(params, "status")),
    started_after: null,
    started_before: null,
    cursor: parseCursor(paramGet(params, "cursor")),
    trace_id: null,
    request_id: null,
    run_id: null,
    session_id: null,
    error_code: null,
    completeness: parseCompleteness(paramGet(params, "completeness")),
    capture_mode: null,
  }

  for (const { key, max } of OPTIONAL_STRING_FIELDS) {
    query[key] = optionalBoundedString(paramGet(params, key), max, key)
  }

  return query
}

export function serializeLiveExploreQuery(
  query: LiveExploreQuery,
  options?: { dropCursor?: boolean },
): URLSearchParams {
  const params = new URLSearchParams()
  params.set("limit", String(query.limit))
  for (const { key, omitWhenDropCursor } of SERIALIZE_FIELDS) {
    if (omitWhenDropCursor && options?.dropCursor) continue
    const value = query[key]
    if (value) params.set(key, value)
  }
  return params
}

export function liveExploreHref(query: LiveExploreQuery, options?: { dropCursor?: boolean }): string {
  const params = serializeLiveExploreQuery(query, options)
  const qs = params.toString()
  return qs ? `/dashboard/explore?${qs}` : "/dashboard/explore"
}
