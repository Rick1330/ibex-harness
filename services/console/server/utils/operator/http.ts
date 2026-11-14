import { createHash } from "node:crypto"

import type { H3Event } from "h3"
import {
  appendResponseHeader,
  createError,
  getCookie,
  getHeader,
  getMethod,
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

/**
 * Domain the API issues its session cookies for, when the deployment sets one.
 *
 * The BFF relays the API's `Set-Cookie` headers verbatim on login, so a cookie
 * issued with `Domain=.example.com` is not removed by a host-only deletion. The
 * local deletions must carry the same attribute. A value that is not a bare
 * host suffix is ignored rather than written into a header.
 */
function cookieDomain(): string {
  const raw = process.env.DASHBOARD_COOKIE_DOMAIN?.trim() ?? ""
  return /^\.?[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*$/.test(raw) ? raw : ""
}

/**
 * Session wiring the browser needs before it holds a session: the configured
 * CSRF cookie name and this browser's own double-submit token. Neither is a
 * secret — the CSRF cookie is deliberately readable by same-origin JavaScript.
 */
export function sessionBootstrap(event: H3Event): {
  csrf_cookie_name: string
  csrf_token: string | null
} {
  const name = csrfCookieName()
  return { csrf_cookie_name: name, csrf_token: getCookie(event, name) ?? null }
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

type ReadOptions = {
  suffix?: string
  query?: URLSearchParams
  signal?: AbortSignal
}

/**
 * Read one operator resource.
 *
 * A 401 is answered once with a server-side refresh-and-retry: the access cookie
 * expires long before the refresh cookie, and without this every read failed
 * even though the session was still recoverable. `path` is always an operator
 * read (session routes are not `OperatorPath`s), so a 401 here can never
 * refresh the refresh route itself. The retry is single-shot by construction:
 * `fetchOperatorJsonAttempt` only refreshes while `rotatedAccess` is null.
 */
export async function fetchOperatorJson<T>(
  event: H3Event,
  path: OperatorPath,
  parse: (value: unknown) => T,
  options: ReadOptions = {},
): Promise<T> {
  return fetchOperatorJsonAttempt(event, path, parse, options, null)
}

async function fetchOperatorJsonAttempt<T>(
  event: H3Event,
  path: OperatorPath,
  parse: (value: unknown) => T,
  options: ReadOptions,
  rotatedAccess: string | null,
): Promise<T> {
  const target = operatorTarget(event, path, options.suffix, options.query)
  const cookieHeader = rotatedAccess
    ? `${accessCookieName(event)}=${rotatedAccess}`
    : sessionCookie(event).header
  if (hasCookie(cookieHeader) && target.protocol !== "https:") {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INSECURE",
      "Operator session cookies require an HTTPS API origin",
    )
  }

  const headers = new Headers({ Accept: "application/json" })
  if (cookieHeader) headers.set("Cookie", cookieHeader)

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
    // Recover an expired access cookie once, then retry this exact read with the
    // freshly issued value. The retry never refreshes again, so a second 401
    // falls through to the unauthenticated branch instead of looping.
    if (response.status === 401 && rotatedAccess === null) {
      const rotated = await rotateAccessCookie(event)
      if (rotated) {
        return fetchOperatorJsonAttempt(event, path, parse, options, rotated)
      }
    }
    // Fail closed: no data and no invented payload. Only a browser document
    // navigation may be redirected, because a followed redirect would hand the
    // login page back to the caller as a 200 body and `useAsyncData` would store
    // that HTML as operator data. Every other caller gets a 401 so
    // `isOperatorAuthError` can render the sign-in state.
    if (response.status === 401) {
      if (isDocumentRequest(event)) {
        const location = loginLocation(event)
        sendRedirect(event, location, 302)
        throw new OperatorLoginRedirect(location)
      }
      const parsed = ApiErrorSchema.safeParse(body)
      throw new OperatorUpstreamError(
        401,
        parsed.success ? parsed.data.error.code : "UNAUTHENTICATED",
        parsed.success ? parsed.data.error.message : "Operator session required",
        parsed.success ? (parsed.data.error.request_id ?? null) : null,
      )
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
 * Signals that `fetchOperatorJson` already wrote a redirect response.
 * `toHttpError` must not try to write a second response.
 */
export class OperatorLoginRedirect extends Error {
  readonly location: string

  constructor(location: string) {
    super("Operator login required")
    this.name = "OperatorLoginRedirect"
    this.location = location
  }
}

export function loginLocation(event: H3Event): string {
  const url = getRequestURL(event)
  const next = `${url.pathname}${url.search}`
  return `${LOGIN_PATH}?next=${encodeURIComponent(next)}`
}

/**
 * Whether the caller is a browser navigating to a document.
 *
 * Only a `GET` that explicitly accepts HTML is redirected. An SSR data read
 * cannot be mistaken for one: Nitro's `event.fetch`/`event.$fetch` forwards the
 * outer request headers through h3's `getProxyRequestHeaders`, which drops
 * `accept`, so an internal sub-request arrives here without an HTML `Accept`.
 * That is what keeps a server-rendered data fetch on the 401 path while a real
 * page navigation still gets the redirect.
 */
function isDocumentRequest(event: H3Event): boolean {
  if (getMethod(event) !== "GET") return false
  const accept = (getHeader(event, "accept") ?? "").toLowerCase()
  return accept.includes("text/html")
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
function relaySessionCookies(event: H3Event, response: Response): string[] {
  const cookies = setCookieHeaders(response)
  for (const cookie of cookies) {
    appendResponseHeader(event, "set-cookie", cookie)
  }
  return cookies
}

/** The value of `name` in the first matching `Set-Cookie` header, or null. */
function cookieValueFromSetCookie(cookies: string[], name: string): string | null {
  for (const cookie of cookies) {
    const pair = cookie.split(";", 1)[0] ?? ""
    const separator = pair.indexOf("=")
    if (separator < 0) continue
    if (pair.slice(0, separator).trim() !== name) continue
    const value = pair.slice(separator + 1).trim()
    if (value) return value
  }
  return null
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
  const domain = cookieDomain()
  const domainFlag = domain ? `; Domain=${domain}` : ""
  for (const { name, httpOnly } of deletions) {
    const flags = `Path=/; Max-Age=0; Secure; SameSite=Lax${domainFlag}${httpOnly ? "; HttpOnly" : ""}`
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
  return (await performSessionAction(event, action, body)).payload
}

type SessionOutcome = {
  payload: Record<string, unknown>
  setCookies: string[]
}

async function performSessionAction(
  event: H3Event,
  action: OperatorSessionAction,
  body?: { pat: string },
  options: { csrfFromCookie?: boolean; synthesizeOrigin?: boolean } = {},
): Promise<SessionOutcome> {
  const target = new URL(SESSION_PATHS[action], configuredOrigin(event))
  const headers = new Headers({ Accept: "application/json" })

  const cookie = sessionCookieHeader(event)
  // A session cookie *or* a PAT must never cross a cleartext hop. The PAT guard
  // is independent of cookies on purpose: login has no cookie yet, so a
  // cookie-only guard would send the token in plaintext over `http://`.
  if ((cookie || body) && target.protocol !== "https:") {
    throw new OperatorUpstreamError(
      503,
      "API_ORIGIN_INSECURE",
      "Operator API credentials require an HTTPS origin",
    )
  }
  if (cookie) headers.set("Cookie", cookie)

  const csrf =
    getHeader(event, "x-csrf-token") ??
    (options.csrfFromCookie ? getCookie(event, csrfCookieName()) : undefined)
  if (csrf) headers.set("X-CSRF-Token", csrf)

  // The API's CSRF middleware checks Origin (Referer fallback) outside
  // development, and it checks origin *before* the CSRF token. Forward the
  // browser's own origin when it sent one. A server-side refresh is the one
  // exception: it is driven by a GET that normally carries neither header, so
  // without an Origin the API answers 403 and a valid session is sent to login.
  // Supply this Console's own request origin for that call only. The API
  // validates the value against its CORS_ORIGINS allow-list
  // (`services/api/app/middleware/csrf.py::_origin_allowed`), so a forged Host
  // that yields a different origin is rejected upstream. The cookie/header
  // double-submit proof is unchanged.
  const origin = getHeader(event, "origin")
  if (origin) headers.set("Origin", origin)
  const referer = getHeader(event, "referer")
  if (referer) headers.set("Referer", referer)
  if (!origin && !referer && options.synthesizeOrigin) {
    headers.set("Origin", getRequestURL(event, { xForwardedHost: true }).origin)
  }

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
  const setCookies = relaySessionCookies(event, response)

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
  return { payload: sanitizeSessionPayload(parsed), setCookies }
}

/**
 * In-flight rotations, keyed by a hash of the refresh cookie value.
 *
 * An expiring access cookie makes several parallel reads 401 at once. The API
 * accepts a refresh token once, so without sharing the rotation every loser is
 * treated as an invalid session and the browser is sent to login during an
 * ordinary page load. The map holds the shared promise only while it is in
 * flight; an entry deletes itself when it settles, and the size cap keeps a
 * pathological burst from growing the map without bound. The key is hashed so
 * the raw refresh token is not retained as a map key.
 */
const ROTATIONS_IN_FLIGHT = new Map<string, Promise<string | null>>()
const MAX_ROTATIONS_IN_FLIGHT = 256

function rotationKey(refreshToken: string): string {
  return createHash("sha256").update(refreshToken).digest("hex")
}

/**
 * Rotate the access cookie once, server-side, and return the newly issued value.
 *
 * Returns null when there is no refresh cookie to present or the API refuses to
 * rotate. The rotated `Set-Cookie` headers are relayed to this response; the
 * caller retries the original read with the returned value because the incoming
 * request still carries the expired cookie. Concurrent callers that present the
 * same refresh cookie share one in-flight rotation, so the API's single-use
 * refresh token is not replayed by a second caller.
 *
 * The refresh is a direct `fetch` to the upstream API through
 * `performSessionAction`, which relays `Set-Cookie` to *this* event. Do not
 * reimplement it through `event.$fetch`/`useRequestFetch`: h3's
 * `fetchWithEvent` forwards request headers only and resolves to the parsed
 * body, so an inner route's `Set-Cookie` never reaches the outer SSR response
 * and the browser keeps its stale cookies. A server-render caller that reaches
 * an operator route as a sub-request must use `$fetch.raw()` and relay the
 * response headers itself.
 */
async function rotateAccessCookie(event: H3Event): Promise<string | null> {
  const refreshToken = getCookie(event, refreshCookieName())
  if (!refreshToken) return null

  const key = rotationKey(refreshToken)
  const shared = ROTATIONS_IN_FLIGHT.get(key)
  if (shared) return shared

  if (ROTATIONS_IN_FLIGHT.size >= MAX_ROTATIONS_IN_FLIGHT) {
    // Bound the map, not the rotation: drop the oldest in-flight entry. Its
    // waiters still hold the promise; a new caller starts its own rotation
    // instead of the map growing without limit.
    const oldest = ROTATIONS_IN_FLIGHT.keys().next().value
    if (oldest !== undefined) ROTATIONS_IN_FLIGHT.delete(oldest)
  }

  const rotation = performRefresh(event)
  ROTATIONS_IN_FLIGHT.set(key, rotation)
  try {
    return await rotation
  } finally {
    if (ROTATIONS_IN_FLIGHT.get(key) === rotation) ROTATIONS_IN_FLIGHT.delete(key)
  }
}

async function performRefresh(event: H3Event): Promise<string | null> {
  try {
    const { setCookies } = await performSessionAction(event, "refresh", undefined, {
      // The API enforces CSRF double-submit on refresh. The browser's CSRF
      // cookie arrived with this request; reuse it as the header so a
      // server-side rotation carries the same proof the page would send.
      csrfFromCookie: true,
      // A read is a GET, so it usually carries no Origin/Referer. Supply the
      // Console's own origin so the API's origin check can pass.
      synthesizeOrigin: true,
    })
    return cookieValueFromSetCookie(setCookies, accessCookieName(event))
  } catch {
    return null
  }
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
