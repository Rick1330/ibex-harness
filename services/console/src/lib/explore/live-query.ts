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

export class LiveExploreQueryError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "LiveExploreQueryError"
  }
}

function optionalString(value: string | null | undefined, max: number, label: string): string | null {
  if (value == null || value === "") return null
  if (value.length > max) throw new LiveExploreQueryError(`${label} exceeds maximum length`)
  return value
}

export function parseLiveExploreQuery(
  params: URLSearchParams | Record<string, string | string[] | undefined>,
): LiveExploreQuery {
  const get = (key: string): string | null => {
    if (params instanceof URLSearchParams) return params.get(key)
    const raw = params[key]
    if (Array.isArray(raw)) return raw[0] ?? null
    return raw ?? null
  }

  for (const key of params instanceof URLSearchParams ? params.keys() : Object.keys(params)) {
    if (!ALLOWED.has(key)) throw new LiveExploreQueryError(`Unknown query field: ${key}`)
  }

  const limitRaw = get("limit")
  const limit = limitRaw == null || limitRaw === "" ? 50 : Number(limitRaw)
  if (!Number.isInteger(limit) || limit < 1 || limit > 100) {
    throw new LiveExploreQueryError("limit must be an integer between 1 and 100")
  }

  const statusRaw = get("status")
  let status: LiveExploreQuery["status"] = null
  if (statusRaw === "ok" || statusRaw === "error") status = statusRaw
  else if (statusRaw != null && statusRaw !== "") throw new LiveExploreQueryError("status must be ok or error")

  const completeness = optionalString(get("completeness"), 32, "completeness")
  if (completeness && !COMPLETENESS.has(completeness)) {
    throw new LiveExploreQueryError("invalid completeness")
  }

  const cursor = optionalString(get("cursor"), 2048, "cursor")
  if (cursor && (cursor.includes(" ") || cursor.includes("\n"))) {
    throw new LiveExploreQueryError("invalid cursor")
  }

  return {
    limit,
    status,
    started_after: optionalString(get("started_after"), 64, "started_after"),
    started_before: optionalString(get("started_before"), 64, "started_before"),
    cursor,
    trace_id: optionalString(get("trace_id"), 256, "trace_id"),
    request_id: optionalString(get("request_id"), 256, "request_id"),
    run_id: optionalString(get("run_id"), 36, "run_id"),
    session_id: optionalString(get("session_id"), 36, "session_id"),
    error_code: optionalString(get("error_code"), 128, "error_code"),
    completeness,
    capture_mode: optionalString(get("capture_mode"), 32, "capture_mode"),
  }
}

export function serializeLiveExploreQuery(query: LiveExploreQuery, options?: { dropCursor?: boolean }): URLSearchParams {
  const params = new URLSearchParams()
  params.set("limit", String(query.limit))
  if (query.status) params.set("status", query.status)
  if (query.started_after) params.set("started_after", query.started_after)
  if (query.started_before) params.set("started_before", query.started_before)
  if (!options?.dropCursor && query.cursor) params.set("cursor", query.cursor)
  if (query.trace_id) params.set("trace_id", query.trace_id)
  if (query.request_id) params.set("request_id", query.request_id)
  if (query.run_id) params.set("run_id", query.run_id)
  if (query.session_id) params.set("session_id", query.session_id)
  if (query.error_code) params.set("error_code", query.error_code)
  if (query.completeness) params.set("completeness", query.completeness)
  if (query.capture_mode) params.set("capture_mode", query.capture_mode)
  return params
}

export function liveExploreHref(query: LiveExploreQuery, options?: { dropCursor?: boolean }): string {
  const params = serializeLiveExploreQuery(query, options)
  const qs = params.toString()
  return qs ? `/dashboard/explore?${qs}` : "/dashboard/explore"
}
