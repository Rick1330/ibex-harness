import type { H3Event } from "h3"
import {
  appendResponseHeader,
  createError,
  getCookie,
  getHeader,
  getRequestURL,
  sendRedirect,
  setResponseHeader,
} from "h3"
import { ApiErrorSchema } from "~~/shared/operator/contracts"

const OPERATOR_PATHS = {
  context: "/v1/operator/context",
  overview: "/v1/operator/overview",
  platformHealth: "/v1/operator/platform/health",
  events: "/v1/operator/events/stream",
  traces: "/v1/operator/traces",
  traceDetail: "/v1/operator/traces/",
  runDetail: "/v1/operator/traces/runs/",
  agents: "/v1/operator/agents",
  agentDetail: "/v1/operator/agents/",
  evidenceSummary: "/v1/operator/evidence/summary",
  evidenceDeletions: "/v1/operator/evidence/deletions",
  directives: "/v1/operator/directives",
  directiveDetail: "/v1/operator/directives/",
  memories: "/v1/operator/memories",
  memoryDetail: "/v1/operator/memories/",
  sessions: "/v1/operator/sessions",
  sessionDetail: "/v1/operator/sessions/",
} as const

/**
 * Session endpoints the Console BFF calls. The API owns issuance and revocation;
 * the BFF only relays the upstream response, including its `Set-Cookie` headers,
 * to the Console origin. The upstream origin is never exposed to the browser.
 */
const SESSION_PATHS = {
  login: "/v1/operator/session/login",
  refresh: "/v1/operator/session/refresh",
  logout: "/v1/operator/session/logout",
} as const

export type OperatorSessionAction = keyof typeof SESSION_PATHS

const DEFAULT_REFRESH_COOKIE = "ibex_refresh"
const DEFAULT_CSRF_COOKIE = "ibex_csrf"
const LOGIN_PATH = "/login"
/** Fields a browser needs from a session response; everything else is dropped. */
const SESSION_PAYLOAD_KEYS = ["status", "provisional", "org_id", "csrf_token"] as const

const TRACE_ID_RE = /^[A-Za-z0-9._~-]{1,256}$/
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const SUFFIX_PATHS = new Set<OperatorPath>([
  "traceDetail",
  "runDetail",
  "agentDetail",
  "memoryDetail",
  "sessionDetail",
  "directiveDetail",
])

export type OperatorPath = keyof typeof OPERATOR_PATHS

export class OperatorUpstreamError extends Error {
  readonly status: number
  readonly code: string
  readonly requestId: string | null

  constructor(status: number, code: string, message: string, requestId: string | null = null) {
    super(message)
    this.name = "OperatorUpstreamError"
    this.status = status
    this.code = code
    this.requestId = requestId
  }
}

function configuredOrigin(event: H3Event): URL {
  const config = useRuntimeConfig(event)
  const raw =
    process.env.IBEX_OPERATOR_API_ORIGIN?.trim() ||
    String(config.operatorApiOrigin ?? "").trim()
  if (!raw) {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_UNAVAILABLE",
      "Operator API origin is unavailable",
    )
  }

  let origin: URL
  try {
    origin = new URL(raw)
  } catch {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INVALID",
      "Operator API origin is invalid",
    )
  }

  const hasUserinfo = Boolean(origin.username || origin.password)
  const hasPath = origin.pathname !== "/" || Boolean(origin.search) || Boolean(origin.hash)
  const protocolAllowed = origin.protocol === "http:" || origin.protocol === "https:"
  if (!protocolAllowed || hasUserinfo || hasPath) {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INVALID",
      "Operator API origin is invalid",
    )
  }
  return origin
}

export function operatorTarget(
  event: H3Event,
  path: OperatorPath,
  suffix = "",
  query?: URLSearchParams,
): URL {
  const origin = configuredOrigin(event)
  if (suffix && !SUFFIX_PATHS.has(path)) {
    throw new OperatorUpstreamError(404, "NOT_FOUND", "Not found")
  }
  if (suffix) {
    // Record-detail routes take UUIDs. Keeping directiveDetail on TRACE_ID_RE
    // would accept "." and "..", and `new URL()` would resolve the suffix away
    // from the intended upstream path while still carrying the session cookie.
    const uuidSuffix =
      path === "agentDetail" ||
      path === "memoryDetail" ||
      path === "sessionDetail" ||
      path === "directiveDetail"
    const pattern = uuidSuffix ? UUID_RE : TRACE_ID_RE
    if (!pattern.test(suffix)) {
      throw new OperatorUpstreamError(404, "NOT_FOUND", "Not found")
    }
  }

  const target = new URL(`${OPERATOR_PATHS[path]}${encodeURIComponent(suffix)}`, origin)
  // Defense in depth: no suffix may move the request to a different upstream path.
  if (suffix && !target.pathname.startsWith(OPERATOR_PATHS[path])) {
    throw new OperatorUpstreamError(404, "NOT_FOUND", "Not found")
  }
  if (query) target.search = query.toString()
  if (target.origin !== origin.origin) {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INVALID",
      "Operator API origin is invalid",
    )
  }
  return target
}

function accessCookieName(event: H3Event): string {
  const config = useRuntimeConfig(event)
  return (
    process.env.IBEX_OPERATOR_SESSION_COOKIE_NAME?.trim() ||
    String(config.operatorSessionCookieName ?? "ibex_session")
  )
}

function refreshCookieName(): string {
  return process.env.IBEX_OPERATOR_REFRESH_COOKIE_NAME?.trim() || DEFAULT_REFRESH_COOKIE
}

function csrfCookieName(): string {
  return process.env.IBEX_OPERATOR_CSRF_COOKIE_NAME?.trim() || DEFAULT_CSRF_COOKIE
}

export function sessionCookie(event: H3Event): { name: string; header: string } {
  const name = accessCookieName(event)
  const value = getCookie(event, name)
  return { name, header: value ? `${name}=${value}` : "" }
}

/**
 * Cookie header for session endpoints. Unlike the read path, refresh and logout
 * need the refresh cookie and the double-submit CSRF cookie, so all three known
 * session cookies are forwarded and nothing else is.
 */
export function sessionCookieHeader(event: H3Event): string {
  const names = [accessCookieName(event), refreshCookieName(), csrfCookieName()]
  return names
    .map((name) => {
      const value = getCookie(event, name)
      return value ? `${name}=${value}` : ""
    })
    .filter(Boolean)
    .join("; ")
}

function hasCookie(header: string): boolean {
  return header.trim().length > 0
}

const JSON_MEDIA_TYPE = "application/json"

function bodyError(statusCode: number, code: string, message: string): never {
  throw createError({
    statusCode,
    statusMessage: message,
    data: { error: { code, message } },
  })
}

/**
 * Read the request body while refusing to buffer more than `maxBytes`.
 *
 * `readRawBody`/`readBody` buffer every chunk with no limit, so a
 * `Transfer-Encoding: chunked` request that omits `Content-Length` would bypass
 * a header-only cap. This reader aborts at the cap instead of trusting the
 * declared length, then resumes (drains) the request so the connection is not
 * left half-read.
 */
function readCappedRawBody(event: H3Event, maxBytes: number): Promise<Buffer> {
  const req = event.node.req
  return new Promise<Buffer>((resolve, reject) => {
    const chunks: Buffer[] = []
    let total = 0

    const cleanup = (): void => {
      req.off("data", onData)
      req.off("end", onEnd)
      req.off("error", onError)
    }
    const onData = (chunk: Buffer | string): void => {
      const buffer = typeof chunk === "string" ? Buffer.from(chunk) : chunk
      total += buffer.byteLength
      if (total > maxBytes) {
        cleanup()
        req.resume()
        reject(createError({
          statusCode: 413,
          statusMessage: "Request body is too large",
          data: { error: { code: "PAYLOAD_TOO_LARGE", message: "Request body is too large." } },
        }))
        return
      }
      chunks.push(buffer)
    }
    const onEnd = (): void => {
      cleanup()
      resolve(Buffer.concat(chunks))
    }
    const onError = (error: unknown): void => {
      cleanup()
      reject(error)
    }

    req.on("data", onData).on("end", onEnd).on("error", onError)
  })
}

/**
 * Parse a JSON request body under a hard byte cap.
 *
 * The unauthenticated login route is the reason this exists: `Content-Length`
 * is attacker-controlled and can be absent entirely, so the cap is enforced
 * twice — a missing or oversized declared length is rejected before reading,
 * and the actual bytes are counted while reading so a lying header cannot
 * smuggle a larger body through. `application/json` is required, which also
 * blocks a cross-site HTML form (a form cannot set that content type without a
 * CORS preflight).
 */
export async function readJsonBodyCapped(
  event: H3Event,
  maxBytes: number,
): Promise<unknown> {
  const contentType = (getHeader(event, "content-type") ?? "").toLowerCase()
  const mediaType = contentType.split(";")[0]?.trim() ?? ""
  if (mediaType !== JSON_MEDIA_TYPE) {
    bodyError(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json.")
  }

  const declaredHeader = getHeader(event, "content-length")
  const declaredLength = declaredHeader === undefined ? Number.NaN : Number(declaredHeader)
  if (!Number.isFinite(declaredLength) || declaredLength < 0 || declaredLength > maxBytes) {
    bodyError(413, "PAYLOAD_TOO_LARGE", "Request body is too large.")
  }

  const raw = await readCappedRawBody(event, maxBytes)
  if (raw.byteLength > maxBytes) {
    bodyError(413, "PAYLOAD_TOO_LARGE", "Request body is too large.")
  }
  if (raw.byteLength === 0) return null

  try {
    return JSON.parse(raw.toString("utf8")) as unknown
  } catch {
    bodyError(400, "INVALID_REQUEST", "Request body must be valid JSON.")
  }
}

export async function fetchOperatorJson<T>(
  event: H3Event,
  path: OperatorPath,
  parse: (value: unknown) => T,
  options: {
    suffix?: string
    query?: URLSearchParams
    signal?: AbortSignal
  } = {},
): Promise<T> {
  const target = operatorTarget(event, path, options.suffix, options.query)
  const cookie = sessionCookie(event)
  if (hasCookie(cookie.header) && target.protocol !== "https:") {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INSECURE",
      "Operator session cookies require an HTTPS API origin",
    )
  }

  const headers = new Headers({ Accept: "application/json" })
  if (cookie.header) headers.set("Cookie", cookie.header)

  let response: Response
  try {
    response = await fetch(target, {
      cache: "no-store",
      redirect: "error",
      signal: options.signal ?? AbortSignal.timeout(5_000),
      headers,
    })
  } catch {
    throw new OperatorUpstreamError(
      503,
      "OPERATOR_API_UNREACHABLE",
      "Operator API is unavailable",
    )
  }

  const body: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    // A document request (a real browser navigation) that reaches a BFF route
    // with an expired session is sent to the login page instead of a raw JSON
    // error. Server-render data fetches strip `Accept`, so they keep the
    // fail-closed 401 below and the page renders its normal auth-error state.
    if (response.status === 401 && isDocumentRequest(event)) {
      const location = loginLocation(event)
      sendRedirect(event, location, 302)
      throw new OperatorLoginRedirect(location)
    }
    const parsed = ApiErrorSchema.safeParse(body)
    throw new OperatorUpstreamError(
      response.status,
      parsed.success ? parsed.data.error.code : "API_REQUEST_FAILED",
      parsed.success ? parsed.data.error.message : "Operator API request failed",
      parsed.success ? (parsed.data.error.request_id ?? null) : null,
    )
  }

  try {
    return parse(body)
  } catch {
    throw new OperatorUpstreamError(
      502,
      "INVALID_UPSTREAM_PAYLOAD",
      "Operator API returned an invalid payload",
    )
  }
}

/**
 * Signals that `fetchOperatorJson` already wrote a redirect response for a
 * document load. `toHttpError` must not try to write a second response.
 */
export class OperatorLoginRedirect extends Error {
  readonly location: string

  constructor(location: string) {
    super("Operator login required")
    this.name = "OperatorLoginRedirect"
    this.location = location
  }
}

/** A browser navigation, not a server-render or XHR data fetch. */
function isDocumentRequest(event: H3Event): boolean {
  return (getHeader(event, "accept") ?? "").toLowerCase().includes("text/html")
}

export function loginLocation(event: H3Event): string {
  const url = getRequestURL(event)
  const next = `${url.pathname}${url.search}`
  return `${LOGIN_PATH}?next=${encodeURIComponent(next)}`
}

function setCookieHeaders(response: Response): string[] {
  const headers = response.headers as Headers & { getSetCookie?: () => string[] }
  if (typeof headers.getSetCookie === "function") return headers.getSetCookie()
  const combined = headers.get("set-cookie")
  return combined ? [combined] : []
}

/**
 * Relay upstream `Set-Cookie` headers verbatim to the Console origin. Cookie
 * flags (HttpOnly, Secure, SameSite, Domain, Max-Age) are the API's decision and
 * are never rewritten here.
 */
function relaySessionCookies(event: H3Event, response: Response): void {
  for (const cookie of setCookieHeaders(response)) {
    appendResponseHeader(event, "set-cookie", cookie)
  }
}

/**
 * Append unconditional deletions for every known session cookie.
 *
 * Logout cannot rely on the API's relayed deletions: its CSRF middleware rejects
 * a request with a missing or mismatched token *before* the handler runs, so no
 * deletion cookie is ever produced. Without this the browser keeps a valid
 * session cookie after the user signs out. The CSRF cookie is deliberately not
 * HttpOnly so the client can read it back for the double-submit header.
 */
export function appendSessionDeletionCookies(event: H3Event): void {
  const deletions: Array<{ name: string; httpOnly: boolean }> = [
    { name: accessCookieName(event), httpOnly: true },
    { name: refreshCookieName(), httpOnly: true },
    { name: csrfCookieName(), httpOnly: false },
  ]
  for (const { name, httpOnly } of deletions) {
    const flags = `Path=/; Max-Age=0; Secure; SameSite=Lax${httpOnly ? "; HttpOnly" : ""}`
    appendResponseHeader(event, "set-cookie", `${name}=; ${flags}`)
  }
}

function sanitizeSessionPayload(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object") return {}
  const source = value as Record<string, unknown>
  const payload: Record<string, unknown> = {}
  for (const key of SESSION_PAYLOAD_KEYS) {
    if (key in source) payload[key] = source[key]
  }
  return payload
}

/**
 * POST a session action to the operator API and relay its cookies back to the
 * browser. The PAT and cookie values are never logged. The upstream origin
 * stays server-side; the browser only ever sees this same-origin route.
 */
export async function callOperatorSession(
  event: H3Event,
  action: OperatorSessionAction,
  body?: { pat: string },
): Promise<Record<string, unknown>> {
  const target = new URL(SESSION_PATHS[action], configuredOrigin(event))
  const headers = new Headers({ Accept: "application/json" })

  const cookie = sessionCookieHeader(event)
  // Match the read path: never send session cookies to a cleartext origin.
  if (cookie && target.protocol !== "https:") {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INSECURE",
      "Operator session cookies require an HTTPS API origin",
    )
  }
  if (cookie) headers.set("Cookie", cookie)

  const csrf = getHeader(event, "x-csrf-token")
  if (csrf) headers.set("X-CSRF-Token", csrf)

  // The API's CSRF middleware checks Origin (Referer fallback) outside
  // development. Forward the browser's own origin; never synthesize one.
  const origin = getHeader(event, "origin")
  if (origin) headers.set("Origin", origin)
  const referer = getHeader(event, "referer")
  if (referer) headers.set("Referer", referer)

  let payload: string | undefined
  if (body) {
    headers.set("Content-Type", "application/json")
    payload = JSON.stringify({ pat: body.pat })
  }

  let response: Response
  try {
    response = await fetch(target, {
      method: "POST",
      headers,
      body: payload,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(5_000),
    })
  } catch {
    throw new OperatorUpstreamError(
      503,
      "OPERATOR_API_UNREACHABLE",
      "Operator API is unavailable",
    )
  }

  // Relay before the status check: logout clears cookies even when it reports
  // an invalid session, so the browser must still receive the deletions.
  relaySessionCookies(event, response)

  const parsed: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const apiError = ApiErrorSchema.safeParse(parsed)
    throw new OperatorUpstreamError(
      response.status,
      apiError.success ? apiError.data.error.code : "SESSION_REQUEST_FAILED",
      apiError.success ? apiError.data.error.message : "Operator session request failed",
      apiError.success ? (apiError.data.error.request_id ?? null) : null,
    )
  }
  return sanitizeSessionPayload(parsed)
}

function loginErrorMessage(statusCode: number): string {
  if (statusCode === 401 || statusCode === 403) {
    return "That personal access token was not accepted."
  }
  if (statusCode === 429) return "Too many sign-in attempts. Wait a moment and try again."
  if (statusCode === 503) {
    return "The operator API is unavailable right now. Try again shortly."
  }
  return "Sign-in failed. Try again."
}

export function noStore(event: H3Event): void {
  setResponseHeader(event, "Cache-Control", "private, no-store")
  setResponseHeader(event, "Vary", "Cookie")
}

export function toHttpError(error: unknown, options: { login?: boolean } = {}): never {
  if (error instanceof OperatorLoginRedirect) {
    // The redirect response is already written; nothing else may be sent.
    return undefined as never
  }
  if (error instanceof OperatorUpstreamError) {
    const statusCode = error.status >= 400 && error.status <= 599 ? error.status : 502
    const message = options.login ? loginErrorMessage(statusCode) : error.message
    throw createError({
      statusCode,
      statusMessage: message,
      data: {
        error: {
          code: error.code,
          message,
          ...(error.requestId ? { request_id: error.requestId } : {}),
        },
      },
    })
  }
  throw createError({
    statusCode: 503,
    statusMessage: "Operator API is unavailable",
    data: {
      error: {
        code: "OPERATOR_API_UNAVAILABLE",
        message: "Operator API is unavailable",
      },
    },
  })
}
