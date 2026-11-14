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
  options: {
    csrfFromCookie?: boolean
    synthesizeOrigin?: boolean
    /**
     * Relay `Set-Cookie` to `event` here. The rotation path sets this to false
     * and relays the retained headers itself, so every response that uses the
     * rotation carries them — not only the one that happened to start it.
     */
    relayCookies?: boolean
  } = {},
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
  // an invalid session, so the browser must still receive the deletions. A
  // rotation opts out and relays from the cache instead (see `relayRotation`).
  const setCookies =
    options.relayCookies === false
      ? setCookieHeaders(response)
      : relaySessionCookies(event, response)

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
 * Rotations shared by a hash of the refresh cookie value.
 *
 * An expiring access cookie makes several reads 401 at once. The API accepts a
 * refresh token once, so a rotation is shared in two ways:
 *
 * - while it is in flight, every overlapping read awaits the same promise;
 * - after it settles, the resolved value is retained for `ROTATION_TTL_MS`, so
 *   a caller that arrives *later* with the same refresh token is served the
 *   rotated value instead of replaying a token the API has already consumed.
 *
 * The second half is what a server render needs, and it is not a race. The
 * outer request's `Cookie` header never changes during a render, so every SSR
 * read that starts after the first rotation settled presents the expired access
 * cookie *and* the consumed refresh token. Two `useAsyncData` calls in a layout
 * and a page are enough to reach this. Without the retained value the second
 * read 401s, a valid session renders as signed out, and an API that treats a
 * replayed refresh token as reuse may revoke the whole session family.
 *
 * A rotation is retained together with the `Set-Cookie` headers it produced,
 * because the browser must receive them on *every* response that uses the
 * rotation. If the initiating response is cancelled or lost after the refresh
 * succeeded, a later cached hit still carries the rotated cookies; without them
 * the browser keeps the expired access cookie and the consumed refresh token.
 *
 * Retaining the value grants no new authority: a caller that presents the
 * refresh token already holds it, and what is retained is the access cookie
 * that token bought. The key is a hash, so the raw token is never a map key,
 * and the map is bounded in both size and time. A failed rotation is not
 * retained — it has no value to serve, and keeping it would answer a later
 * attempt from a stale refusal instead of asking the API. A new refresh token
 * hashes to its own key either way.
 */
const ROTATION_TTL_MS = 10_000
/** Exported so the eviction test can fill the map past the cap deliberately. */
export const MAX_CACHED_ROTATIONS = 256

/**
 * One successful rotation: the access value the API issued and the `Set-Cookie`
 * headers that carried it. The headers are kept with the value so a response
 * that reuses the rotation can hand the browser the rotated cookies too.
 */
type RotationResult = {
  access: string
  setCookies: string[]
}

type RotationEntry = {
  /** Settles with the rotation, or null when the rotation failed. */
  readonly promise: Promise<RotationResult | null>
  /** `Date.now()` after which the resolved value is no longer served. */
  expiresAt: number
  /** Removes the entry when the TTL elapses; cleared by any earlier removal. */
  eviction: ReturnType<typeof setTimeout> | null
}

const ROTATIONS = new Map<string, RotationEntry>()

/**
 * Rotation results already relayed to an event, so one response never carries
 * the same `Set-Cookie` twice. The result is one rotation, so a fresh rotation
 * of the same key (after the TTL) relays again.
 */
const RELAYED_RESULTS = new WeakMap<H3Event, WeakSet<RotationResult>>()

function rotationKey(refreshToken: string): string {
  return createHash("sha256").update(refreshToken).digest("hex")
}

function dropRotation(key: string): void {
  const entry = ROTATIONS.get(key)
  if (!entry) return
  ROTATIONS.delete(key)
  // A timer left behind would fire against a key that may already hold a new
  // rotation, so every removal path clears it.
  if (entry.eviction) clearTimeout(entry.eviction)
}

/**
 * Drop every retained rotation. Tests call this so module state does not carry
 * between cases; production code never needs it.
 */
export function resetRotationCache(): void {
  for (const key of [...ROTATIONS.keys()]) dropRotation(key)
}

/**
 * Relay a rotation's `Set-Cookie` headers to `event`, then return its access
 * value.
 *
 * Every response that uses the rotation calls this — the one that initiated it,
 * a concurrent waiter, and a later cached hit — so a browser that missed the
 * initiating response still receives the rotated cookies. Relaying is
 * idempotent per event and rotation result, so a response never carries the
 * same cookie twice. A failed rotation (`null`) relays nothing and yields
 * `null`, leaving the caller to fail closed.
 */
function relayRotation(event: H3Event, result: RotationResult | null): string | null {
  if (!result) return null
  let relayed = RELAYED_RESULTS.get(event)
  if (!relayed) {
    relayed = new WeakSet<RotationResult>()
    RELAYED_RESULTS.set(event, relayed)
  }
  if (!relayed.has(result)) {
    relayed.add(result)
    for (const cookie of result.setCookies) {
      appendResponseHeader(event, "set-cookie", cookie)
    }
  }
  return result.access
}

/**
 * Eviction policy: drop only a settled rotation whose window has elapsed.
 *
 * An in-flight rotation must never be removed. Its refresh token has already
 * been presented upstream, so a later read that missed the entry would present
 * the same token again; the API accepts each refresh token once and treats
 * reuse as a signal to revoke the whole session family. A settled entry inside
 * its window is kept for the same reason — it can still be evicted and its
 * token replayed. If nothing is evictable the map is allowed to exceed
 * `MAX_CACHED_ROTATIONS` rather than dropping a live rotation; each entry's
 * eviction timer removes it as its window elapses, bringing the map back under
 * the cap without ever replaying a token.
 */
function evictRotations(): void {
  const now = Date.now()
  for (const [key, entry] of [...ROTATIONS]) {
    if (now >= entry.expiresAt) dropRotation(key)
  }
}

/**
 * Keep a settled rotation, or drop it when there is no value to keep.
 *
 * Only one settle handler runs per rotation, so exactly one eviction timer is
 * scheduled however many callers await it. A `null` result is a failed
 * rotation: it is dropped rather than retained, so the map holds no dead entry
 * and a later attempt is asked of the API instead of being answered from a
 * stale refusal.
 */
function settleRotation(
  key: string,
  entry: RotationEntry,
  result: RotationResult | null,
): void {
  if (ROTATIONS.get(key) !== entry) return
  if (result === null) {
    dropRotation(key)
    return
  }
  entry.expiresAt = Date.now() + ROTATION_TTL_MS
  const eviction = setTimeout(() => {
    if (ROTATIONS.get(key) !== entry) return
    entry.eviction = null
    ROTATIONS.delete(key)
  }, ROTATION_TTL_MS)
  // A pending eviction must never keep the process alive.
  eviction.unref?.()
  entry.eviction = eviction
}

/**
 * Rotate the access cookie once, server-side, and return the newly issued value.
 *
 * Returns null when there is no refresh cookie to present or the API refuses to
 * rotate. The rotated `Set-Cookie` headers are relayed to this response whether
 * the rotation was started here, awaited in flight, or served from the retained
 * value; the caller retries the original read with the returned value because
 * the incoming request still carries the expired cookie. Callers that present
 * the same refresh cookie share one rotation — concurrently through the
 * promise, and afterwards through the retained value — so the API's single-use
 * refresh token is never replayed by a second caller.
 *
 * The refresh is a direct `fetch` to the upstream API through
 * `performSessionAction` with `relayCookies: false`; the retained result is the
 * single relay point, so every response that uses the rotation receives the
 * cookies. Do not reimplement it through `event.$fetch`/`useRequestFetch`: h3's
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
  const cached = ROTATIONS.get(key)
  if (cached) {
    // Expire on read as well as on the timer: a timer that has not run yet must
    // not serve a value past its TTL.
    if (Date.now() < cached.expiresAt) return relayRotation(event, await cached.promise)
    dropRotation(key)
  }

  if (ROTATIONS.size >= MAX_CACHED_ROTATIONS) evictRotations()

  const entry: RotationEntry = {
    promise: performRefresh(event),
    // In flight: served to every overlapping caller until it settles.
    expiresAt: Number.POSITIVE_INFINITY,
    eviction: null,
  }
  ROTATIONS.set(key, entry)
  // `performRefresh` answers null rather than rejecting, but a rejection must
  // still leave no cached entry and no unhandled rejection behind.
  void entry.promise
    .then((result) => settleRotation(key, entry, result))
    .catch(() => {
      if (ROTATIONS.get(key) === entry) dropRotation(key)
    })
  return relayRotation(event, await entry.promise)
}

async function performRefresh(event: H3Event): Promise<RotationResult | null> {
  try {
    const { setCookies } = await performSessionAction(event, "refresh", undefined, {
      // The API enforces CSRF double-submit on refresh. The browser's CSRF
      // cookie arrived with this request; reuse it as the header so a
      // server-side rotation carries the same proof the page would send.
      csrfFromCookie: true,
      // A read is a GET, so it usually carries no Origin/Referer. Supply the
      // Console's own origin so the API's origin check can pass.
      synthesizeOrigin: true,
      // Relayed from the retained rotation to every response that uses it.
      relayCookies: false,
    })
    const access = cookieValueFromSetCookie(setCookies, accessCookieName(event))
    return access ? { access, setCookies } : null
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
