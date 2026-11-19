import { execFileSync, spawn } from "node:child_process"
import { createServer } from "node:https"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join, resolve } from "node:path"
import { fileURLToPath } from "node:url"

const consoleDir = dirname(dirname(fileURLToPath(import.meta.url)))
const tempDir = mkdtempSync(join(tmpdir(), "ibex-console-live-"))
const keyPath = join(tempDir, "server.key")
const certPath = join(tempDir, "server.crt")
const apiPort = 3283
const consolePort = 3282
const consoleOrigin = `https://127.0.0.1:${consolePort}`
const observedAt = "2026-09-26T17:00:00Z"

/**
 * The access token `live-d1.spec.ts` mints directly. It is kept so that suite
 * still exercises the read path, and it binds to org A. The session journeys do
 * not use it: they obtain a token from `POST /v1/operator/session/login` exactly
 * as the browser does.
 */
const LEGACY_FIXTURE_ACCESS = "fixture-access-secret"

const SESSION_COOKIE = "ibex_session"
const REFRESH_COOKIE = "ibex_refresh"
const CSRF_COOKIE = "ibex_csrf"

/**
 * Two tenants behind one stand-in operator API.
 *
 * The stand-in issues a session per PAT and resolves every read through that
 * session's org, so a record id belonging to the other org is a 404 — which is
 * what the real API's tenant-scoped queries do. Distinct ids per org are what
 * make the browser-level negative meaningful: org A's session must ask for an id
 * that exists *somewhere* and still be told it does not exist.
 */
const ORG_A = {
  key: "a",
  id: "bfc3f97b-7a61-498d-9faa-96f34fbd4f2f",
  name: "Live Workspace",
  slug: "live-workspace",
  pat: "pat-live-workspace-fixture",
  runId: "11111111-1111-4111-8111-111111111111",
  traceId: "trace-live-1",
  agentId: "33333333-3333-4333-8333-333333333333",
  agentSlug: "support-agent",
  agentName: "Support Agent",
  agentDescription: "Answers customer questions from the memory store.",
  memoryId: "44444444-4444-4444-8444-444444444444",
  sessionId: "88888888-8888-4888-8888-888888888888",
  activeUsers: 7,
  agents: 3,
  activeAgents: 2,
}

const ORG_B = {
  key: "b",
  id: "c1d2e3f4-a5b6-47c8-9d0e-1f2a3b4c5d6e",
  name: "Second Workspace",
  slug: "second-workspace",
  pat: "pat-second-workspace-fixture",
  runId: "22222222-2222-4222-8222-222222222222",
  traceId: "trace-second-1",
  agentId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  agentSlug: "billing-agent",
  agentName: "Billing Agent",
  agentDescription: "Reconciles invoices from the memory store.",
  memoryId: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
  sessionId: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
  activeUsers: 4,
  agents: 1,
  activeAgents: 1,
}

const ORGS = [ORG_A, ORG_B]
const requests = []
/**
 * Transient failures for the retry journeys: `pathname -> { remaining, status }`.
 * A read that fails once must be retryable by the surface that shows it, and the
 * only honest way to test that is to fail the read the way a dependency would.
 */
const faults = new Map()
/** access token -> { orgKey, family } */
const liveAccess = new Map()
/** refresh token -> { orgKey, family, consumed } */
const liveRefresh = new Map()
/** family id -> { revoked } */
const families = new Map()
let eventStreams = 0
let closing = false
let consoleProcess

function assertUnderTempDir(candidate) {
  const resolved = resolve(candidate)
  const root = resolve(tempDir)
  if (resolved !== root && !resolved.startsWith(`${root}/`)) {
    throw new Error(`TLS material path escaped temp dir: ${candidate}`)
  }
  return resolved
}

function writeJson(response, status, body, extraHeaders = {}, entry = null) {
  if (entry) entry.status = status
  response.writeHead(status, {
    "content-type": "application/json",
    "cache-control": "no-store",
    ...extraHeaders,
  })
  response.end(JSON.stringify(body))
}

function writeUnauthorized(response, entry = null) {
  writeJson(
    response,
    401,
    { error: { code: "INVALID_SESSION", message: "Session required" } },
    {},
    entry,
  )
}

/** Read a request body under a hard cap, without trusting `Content-Length`. */
function readBody(request, limit = 8 * 1024) {
  return new Promise((resolve) => {
    const chunks = []
    let total = 0
    let aborted = false
    request.on("data", (chunk) => {
      total += chunk.length
      if (total > limit) {
        aborted = true
        request.resume()
        resolve(null)
        return
      }
      if (!aborted) chunks.push(chunk)
    })
    request.on("end", () => {
      if (!aborted) resolve(Buffer.concat(chunks).toString("utf8"))
    })
    request.on("error", () => {
      if (!aborted) resolve(null)
    })
  })
}

function parseJson(raw) {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/**
 * The stand-in API's session rules.
 *
 * These are the parts of `services/api/app/routers/session.py` the Console's BFF
 * depends on, expressed at the same strength: a PAT exchange issues an HttpOnly
 * access cookie, an HttpOnly refresh cookie and a JavaScript-readable CSRF
 * cookie; refresh is single-use and rotates all three *inside the existing
 * token family*; reuse revokes that family; logout revokes it; and every
 * state-changing call is protected by the origin rule and then the
 * cookie/header double-submit proof, in that order. A stand-in that skipped any
 * of this would let the Console's relay pass a test the real API would fail.
 *
 * Family continuity is the property, not a detail. `RefreshPair`
 * (`services/auth/internal/sessionjwt/jwt.go`) rotates with
 * `FamilyID: FamilyID(claims.FamilyID)` — the new pair carries the refresh
 * token's own family. So a replayed consumed token revokes the family the
 * *rotated* pair belongs to, and the tokens that rotation issued die with it.
 */

function parseCookies(header) {
  const cookies = {}
  for (const part of String(header ?? "").split(";")) {
    const separator = part.indexOf("=")
    if (separator < 0) continue
    const name = part.slice(0, separator).trim()
    if (name) cookies[name] = part.slice(separator + 1).trim()
  }
  return cookies
}

function orgByPat(pat) {
  return ORGS.find((org) => org.pat === pat) ?? null
}

function familyIsLive(familyKey) {
  const family = families.get(familyKey)
  return Boolean(family) && !family.revoked
}

function revokeFamily(familyKey) {
  const family = families.get(familyKey)
  if (family) family.revoked = true
}

/** The org a request's access cookie belongs to, or null. */
function sessionOrg(cookieHeader) {
  const access = parseCookies(cookieHeader)[SESSION_COOKIE]
  if (!access) return null
  if (access === LEGACY_FIXTURE_ACCESS) return ORG_A
  const session = liveAccess.get(access)
  if (!session || !familyIsLive(session.family)) return null
  return ORGS.find((org) => org.key === session.orgKey) ?? null
}

function newToken(prefix) {
  return `${prefix}-${crypto.randomUUID()}`
}

function sessionCookieHeaders({ access, refresh, csrf }) {
  const headers = [
    `${SESSION_COOKIE}=${access}; Path=/; HttpOnly; Secure; SameSite=Lax`,
    `${REFRESH_COOKIE}=${refresh}; Path=/; HttpOnly; Secure; SameSite=Lax`,
    `${CSRF_COOKIE}=${csrf}; Path=/; Secure; SameSite=Lax`,
  ]
  return headers
}

/**
 * Mint a session pair, optionally inside an existing family.
 *
 * A login passes no family and mints one; a rotation passes the consumed
 * refresh token's family, so the rotated pair is a descendant of the same
 * family and shares its revocation.
 */
function issueSession(org, familyKey = newToken("fam")) {
  if (!families.has(familyKey)) families.set(familyKey, { revoked: false })
  const access = newToken("access")
  const refresh = newToken("refresh")
  const csrf = newToken("csrf")
  liveAccess.set(access, { orgKey: org.key, family: familyKey })
  liveRefresh.set(refresh, { orgKey: org.key, family: familyKey, consumed: false })
  return { access, refresh, csrf, family: familyKey }
}

function dropAccess(access) {
  const session = liveAccess.get(access)
  if (!session) return
  liveAccess.delete(access)
  const family = families.get(session.family)
  if (family) family.revoked = true
}

function sessionPayload(org, csrf) {
  return { status: "ok", provisional: false, org_id: org.id, csrf_token: csrf }
}

function csrfAccepted(request, cookies) {
  const header = request.headers["x-csrf-token"]
  const cookie = cookies[CSRF_COOKIE]
  return Boolean(header) && Boolean(cookie) && header === cookie
}

/**
 * The API rejects a cross-origin state-changing request before its handler runs.
 *
 * This mirrors `CSRFMiddleware._origin_allowed`
 * (`services/api/app/middleware/csrf.py`): an `Origin` must be in the allowed
 * list; with no `Origin`, a `Referer` whose `scheme://netloc` is allowed is the
 * fallback; neither header means reject. A missing `Origin` is not permission.
 */
function originAccepted(request) {
  const allowed = [consoleOrigin]
  const origin = request.headers.origin
  if (origin) return allowed.includes(origin)
  const referer = request.headers.referer
  if (!referer) return false
  try {
    const parsed = new URL(referer)
    return allowed.includes(`${parsed.protocol}//${parsed.host}`)
  } catch {
    return false
  }
}

function rejectSession(response, entry, status, code, message) {
  writeJson(response, status, { error: { code, message } }, {}, entry)
  return true
}

function issueSessionResponse(response, entry, org, issued) {
  writeJson(
    response,
    200,
    sessionPayload(org, issued.csrf),
    { "set-cookie": sessionCookieHeaders(issued) },
    entry,
  )
  return true
}

function handleLogin(request, response, body, entry) {
  if (!originAccepted(request)) {
    return rejectSession(response, entry, 403, "ORIGIN_REJECTED", "Origin rejected")
  }
  const pat = typeof body?.pat === "string" ? body.pat.trim() : ""
  const org = orgByPat(pat)
  if (!org) {
    return rejectSession(response, entry, 401, "INVALID_TOKEN", "invalid personal access token")
  }
  return issueSessionResponse(response, entry, org, issueSession(org))
}

function handleRefresh(request, response, entry) {
  // Middleware order upstream: the origin rule first, then the CSRF
  // double-submit proof, then the handler. A request missing either proof never
  // reaches it.
  if (!originAccepted(request)) {
    return rejectSession(response, entry, 403, "ORIGIN_REJECTED", "Origin rejected")
  }
  const cookies = parseCookies(request.headers.cookie)
  if (!csrfAccepted(request, cookies)) {
    return rejectSession(response, entry, 403, "CSRF_FAILED", "CSRF token rejected")
  }
  const refresh = liveRefresh.get(cookies[REFRESH_COOKIE] ?? "")
  if (!refresh || !familyIsLive(refresh.family)) {
    return rejectSession(response, entry, 401, "INVALID_TOKEN", "invalid refresh token")
  }
  if (refresh.consumed) {
    // Replay of a consumed refresh token is treated as family compromise: every
    // descendant of that family, including the pair the rotation issued, dies.
    revokeFamily(refresh.family)
    return rejectSession(response, entry, 401, "INVALID_TOKEN", "invalid refresh token")
  }
  const org = ORGS.find((candidate) => candidate.key === refresh.orgKey)
  refresh.consumed = true
  // Rotation stays inside the refresh token's family (jwt.go::RefreshPair passes
  // `FamilyID: FamilyID(claims.FamilyID)`), so revoking the family is what kills
  // the rotated pair.
  return issueSessionResponse(response, entry, org, issueSession(org, refresh.family))
}

function handleLogout(request, response, entry) {
  if (!originAccepted(request)) {
    return rejectSession(response, entry, 403, "ORIGIN_REJECTED", "Origin rejected")
  }
  const cookies = parseCookies(request.headers.cookie)
  if (!csrfAccepted(request, cookies)) {
    return rejectSession(response, entry, 403, "CSRF_FAILED", "CSRF token rejected")
  }
  const refresh = liveRefresh.get(cookies[REFRESH_COOKIE] ?? "")
  // Revoke the family the session belongs to, whichever cookie proves it.
  if (cookies[SESSION_COOKIE]) dropAccess(cookies[SESSION_COOKIE])
  if (refresh) revokeFamily(refresh.family)
  const cleared = [SESSION_COOKIE, REFRESH_COOKIE, CSRF_COOKIE].map(
    (name) => `${name}=; Path=/; Max-Age=0; Secure; SameSite=Lax`,
  )
  writeJson(response, 200, { status: "signed_out" }, { "set-cookie": cleared }, entry)
  return true
}

/** Dispatch one of the API's session routes; false when the path is not ours. */
function handleSessionRoute(url, request, response, body, entry) {
  if (url.pathname === "/v1/operator/session/login") {
    return handleLogin(request, response, body, entry)
  }
  if (url.pathname === "/v1/operator/session/refresh") {
    return handleRefresh(request, response, entry)
  }
  if (url.pathname === "/v1/operator/session/logout") {
    return handleLogout(request, response, entry)
  }
  return false
}

async function handleTestRoute(url, request, response) {
  if (url.pathname === "/__test/login") {
    response.writeHead(200, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "set-cookie": `${SESSION_COOKIE}=${LEGACY_FIXTURE_ACCESS}; Path=/; Secure; SameSite=Lax`,
    })
    response.end(`<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><title>IBEX Console fixture session</title></head>
  <body>
    <p>Fixture session set. <a href="https://127.0.0.1:${consolePort}/">Open the console</a>.</p>
    <script>location.replace("https://127.0.0.1:${consolePort}/")</script>
  </body>
</html>`)
    return true
  }
  if (url.pathname === "/__test/requests") {
    writeJson(response, 200, requests)
    return true
  }
  if (url.pathname === "/__test/reset" && request.method === "POST") {
    requests.length = 0
    faults.clear()
    response.writeHead(204, { "cache-control": "no-store" })
    response.end()
    return true
  }
  if (url.pathname === "/__test/fail" && request.method === "POST") {
    const body = parseJson(await readBody(request))
    const target = typeof body?.path === "string" ? body.path : ""
    const count = Number(body?.count ?? 1)
    const status = Number(body?.status ?? 503)
    // Only an operator read route can be failed, so a journey cannot point the
    // control at the session endpoints and undo the auth coverage.
    if (!target.startsWith("/v1/operator/") || target.length > 256) {
      writeJson(response, 400, { error: { code: "BAD_FAULT_PATH", message: "path must be an operator read" } })
      return true
    }
    if (!Number.isInteger(count) || count < 1 || count > 10 || !Number.isInteger(status) || status < 500 || status > 599) {
      writeJson(response, 400, { error: { code: "BAD_FAULT", message: "count 1-10, status 5xx" } })
      return true
    }
    faults.set(target, { remaining: count, status })
    response.writeHead(204, { "cache-control": "no-store" })
    response.end()
    return true
  }
  return false
}

/** The injected status for this pathname, consuming one occurrence, or null. */
function consumeFault(pathname) {
  const fault = faults.get(pathname)
  if (!fault) return null
  fault.remaining -= 1
  if (fault.remaining < 1) faults.delete(pathname)
  return fault.status
}

function recordRequest(request, pathname) {
  const cookie = request.headers.cookie ?? ""
  const cookieNames = cookie
    .split(";")
    .map((part) => part.trim().split("=", 1)[0])
    .filter(Boolean)
  const entry = {
    method: request.method,
    path: pathname,
    cookieNames,
    lastEventId: request.headers["last-event-id"] ?? null,
    // Recorded so a journey can assert which origin the BFF supplied upstream.
    origin: request.headers.origin ?? null,
    referer: request.headers.referer ?? null,
    org: null,
    status: null,
  }
  requests.push(entry)
  return { cookie, entry }
}

function handleEventStream(cookie, response, entry) {
  const org = sessionOrg(cookie)
  if (!org) {
    if (entry) entry.status = 401
    writeUnauthorized(response)
    return
  }
  if (entry) {
    entry.org = org.key
    entry.status = 200
  }
  response.writeHead(200, {
    "content-type": "text/event-stream",
    "cache-control": "no-cache",
    connection: "keep-alive",
  })
  eventStreams += 1
  response.write(
    'retry: 1000\nid: 42\nevent: operator.evidence\ndata: {"payload":"EVENT_PAYLOAD_SHOULD_NOT_RENDER"}\n\n',
  )
  if (eventStreams === 1) {
    const disconnect = setTimeout(() => response.end(), 1000)
    response.on("close", () => clearTimeout(disconnect))
    return
  }
  const heartbeat = setInterval(() => response.write(": heartbeat\n\n"), 15_000)
  response.on("close", () => clearInterval(heartbeat))
}

function fixtureBodies(org) {
  const traceItem = {
    trace_id: org.traceId,
    run_id: org.runId,
    request_id: `request-${org.key}-1`,
    agent_id: null,
    session_id: null,
    checkpoint_id: null,
    status: "ok",
    error_code: null,
    started_at: observedAt,
    ended_at: observedAt,
    duration_ms: 12,
    evidence: {
      schema_version: "evidence.v1",
      capture_mode: "metadata",
      completeness: "partial",
      sample_decision: "kept",
      freshness: "unknown",
      retention: "unknown",
      source: "postgres.evidence_runs",
      source_watermark: "outbox:1",
      publication_state: "published",
      ingestion_lag_ms: 0,
      policy_version: "operator.trace-read.v1",
      observed_at: observedAt,
    },
  }
  const traceList = {
    schema_version: "operator.trace-list.v1",
    query_grammar_version: "operator.trace-query.v1",
    items: [traceItem],
    next_cursor: null,
    truncated: false,
    matched_count: 1,
    returned_count: 1,
    observed_at: observedAt,
    query_start: observedAt,
    query_end: observedAt,
    limit: 50,
  }
  const traceDetail = {
    ...traceItem,
    schema_version: "operator.trace-detail.v1",
    unavailable_sections: [
      "content",
      "events",
      "spans",
      "assembly",
      "candidates",
      "score_explanation",
      "directives",
      "tools",
    ],
    spans: [],
    assembly: null,
    candidates: [],
    directive: null,
    tools: [],
    score_schema_note: null,
  }
  const agent = {
    id: org.agentId,
    slug: org.agentSlug,
    name: org.agentName,
    description: org.agentDescription,
    status: "active",
    default_provider: "openai",
    default_model: "gpt-4.1",
    tags: ["prod", "support"],
    total_sessions: 42,
    total_memories: 128,
    total_tokens_used: 901234,
    last_active_at: observedAt,
    created_at: observedAt,
    updated_at: observedAt,
  }
  const memory = {
    id: org.memoryId,
    agent_id: org.agentId,
    session_id: null,
    category: "factual",
    status: "active",
    source: "extracted",
    confidence: 0.8,
    usefulness_score: 0.5,
    content_tokens: 12,
    retrieval_count: 3,
    last_retrieved_at: observedAt,
    pii_detected: false,
    pii_redacted: false,
    visibility: "agent",
    pinned: false,
    tags: ["support"],
    lifecycle_revision: 1,
    tombstoned: false,
    expires_at: null,
    valid_from: observedAt,
    valid_until: null,
    observed_at: observedAt,
    created_at: observedAt,
    updated_at: observedAt,
  }
  // The list projection is lineage-free by contract; only the detail carries it.
  const memoryDetail = {
    ...memory,
    lineage: {
      superseded_by: null,
      merged_into: null,
      tip: { id: org.memoryId, status: "active", tombstoned: false },
      replaces: [],
      replaced_by: [],
      edges_truncated: false,
    },
  }
  const sessionTurn = {
    id: "99999999-9999-4999-8999-999999999999",
    turn_index: 0,
    request_id: `req-${org.key}-1`,
    input_tokens: 10,
    output_tokens: 20,
    model: "gpt-4.1",
    provider: "openai",
    latency_ms: 100,
    is_streaming: false,
    is_complete: true,
    created_at: observedAt,
    trace: {
      trace_id: org.traceId,
      run_id: org.runId,
      completeness: "complete",
      status: "ok",
      error_code: null,
      started_at: observedAt,
      ended_at: observedAt,
    },
  }
  const session = {
    id: org.sessionId,
    agent_id: org.agentId,
    external_id: `ext-${org.key}-1`,
    status: "completed",
    model: "gpt-4.1",
    provider: "openai",
    directive_version_id: null,
    turn_count: 1,
    total_input_tokens: 10,
    total_output_tokens: 20,
    total_latency_ms: 100,
    last_extracted_turn: 0,
    lifecycle_revision: 1,
    evidence_fence_version: 1,
    created_at: observedAt,
    updated_at: observedAt,
    completed_at: observedAt,
  }
  return {
    sessions: {
      data: [session],
      pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
    },
    session,
    sessionDetail: { ...session, turns: [sessionTurn], turns_truncated: false },
    memoryDetail,
    memories: {
      data: [memory],
      pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
    },
    memory,
    agents: {
      data: [agent],
      pagination: { has_more: false, next_cursor: null, prev_cursor: null, total_count: 1 },
    },
    agent,
    context: {
      schema_version: "operator.context.v1",
      org_id: org.id,
      role: "admin",
      org_name: org.name,
      org_slug: org.slug,
      org_status: "active",
      observed_at: observedAt,
    },
    overview: {
      schema_version: "operator.overview.v1",
      org_id: org.id,
      org_name: org.name,
      org_slug: org.slug,
      org_status: "active",
      counts: {
        active_users: org.activeUsers,
        agents: org.agents,
        active_agents: org.activeAgents,
      },
      observed_at: observedAt,
      completeness: "complete",
    },
    health: {
      dependency_health: { database: "ok", redis: "degraded" },
      last_backup_at: null,
      last_restore_drill: null,
      retention_horizon_days: 30,
      ingestion_lag_seconds: null,
      dlq_depth: null,
      degraded_mode: false,
      outbox_max_aggregate_seq: null,
      deploy_image_digest: null,
      observed_at: observedAt,
    },
    traces: traceList,
    traceDetail,
  }
}

function resolveFixtureBody(pathname, org) {
  const bodies = fixtureBodies(org)
  if (pathname === "/v1/operator/sessions") return { status: 200, payload: bodies.sessions }
  if (pathname === `/v1/operator/sessions/${org.sessionId}`) {
    return { status: 200, payload: bodies.sessionDetail }
  }
  if (pathname.startsWith("/v1/operator/sessions/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Session not found" } } }
  }
  if (pathname === "/v1/operator/memories") return { status: 200, payload: bodies.memories }
  if (pathname === `/v1/operator/memories/${org.memoryId}`) {
    return { status: 200, payload: bodies.memoryDetail }
  }
  if (pathname.startsWith("/v1/operator/memories/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Memory not found" } } }
  }
  if (pathname === "/v1/operator/agents") return { status: 200, payload: bodies.agents }
  if (pathname === `/v1/operator/agents/${org.agentId}`) {
    return { status: 200, payload: bodies.agent }
  }
  if (pathname.startsWith("/v1/operator/agents/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Agent not found" } } }
  }
  if (pathname === "/v1/operator/context") return { status: 200, payload: bodies.context }
  if (pathname === "/v1/operator/overview") return { status: 200, payload: bodies.overview }
  if (pathname === "/v1/operator/platform/health") return { status: 200, payload: bodies.health }
  if (pathname === "/v1/operator/traces") return { status: 200, payload: bodies.traces }
  if (pathname === `/v1/operator/traces/runs/${org.runId}`) {
    return { status: 200, payload: bodies.traceDetail }
  }
  if (pathname === `/v1/operator/traces/${org.traceId}`) return { status: 200, payload: bodies.traces }
  if (pathname.startsWith("/v1/operator/traces/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Trace not found" } } }
  }
  return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Not found" } } }
}

function handleAuthenticatedJson(pathname, org, response, entry) {
  const resolved = resolveFixtureBody(pathname, org)
  writeJson(response, resolved.status, resolved.payload, {}, entry)
}

async function handleApiRequest(request, response) {
  const url = new URL(request.url ?? "/", `https://127.0.0.1:${apiPort}`)
  if (await handleTestRoute(url, request, response)) return

  const { cookie, entry } = recordRequest(request, url.pathname)

  if (url.pathname.startsWith("/v1/operator/session/")) {
    const body = url.pathname === "/v1/operator/session/login"
      ? parseJson(await readBody(request))
      : null
    handleSessionRoute(url, request, response, body, entry)
    return
  }

  if (url.pathname === "/v1/operator/events/stream") {
    handleEventStream(cookie, response, entry)
    return
  }
  const org = sessionOrg(cookie)
  if (!org) {
    writeUnauthorized(response, entry)
    return
  }
  entry.org = org.key
  const faultStatus = consumeFault(url.pathname)
  if (faultStatus !== null) {
    writeJson(
      response,
      faultStatus,
      { error: { code: "INJECTED_UNAVAILABLE", message: "Injected transient failure" } },
      {},
      entry,
    )
    return
  }
  handleAuthenticatedJson(url.pathname, org, response, entry)
}

const previousCwd = process.cwd()
process.chdir(assertUnderTempDir(tempDir))
let tlsKey
let tlsCert
try {
  execFileSync(process.env.OPENSSL_BIN || "openssl", [
    "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
    "-keyout", "server.key", "-out", "server.crt", "-subj", "/CN=127.0.0.1",
    "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
    "-addext", "basicConstraints=critical,CA:TRUE",
  ], { stdio: "ignore" })
  // Literal basenames after chdir — satisfies Codacy non-literal fs.
  tlsKey = readFileSync("server.key")
  tlsCert = readFileSync("server.crt")
} finally {
  process.chdir(previousCwd)
}

const api = createServer({ key: tlsKey, cert: tlsCert }, (request, response) => {
  handleApiRequest(request, response).catch(() => {
    if (response.headersSent) {
      response.end()
      return
    }
    writeJson(response, 500, { error: { code: "STANDIN_FAILED", message: "Stand-in failed" } })
  })
})
api.listen(apiPort, "127.0.0.1")

consoleProcess = spawn(
  "corepack",
  [
    "pnpm", "exec", "nuxt", "dev",
    "--no-tui", "--no-fork",
    "--host", "127.0.0.1", "--port", String(consolePort),
    "--https", "--https.key", keyPath, "--https.cert", certPath,
  ],
  {
    cwd: consoleDir,
    env: {
      ...process.env,
      NODE_EXTRA_CA_CERTS: certPath,
      NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ""} --use-openssl-ca`.trim(),
      SSL_CERT_FILE: certPath,
      CONSOLE_READ_ONLY: "1",
      IBEX_OPERATOR_API_ORIGIN: `https://127.0.0.1:${apiPort}`,
      IBEX_OPERATOR_SESSION_COOKIE_NAME: "ibex_session",
    },
    stdio: "inherit",
  },
)

function shutdown() {
  if (closing) return
  closing = true
  consoleProcess?.kill("SIGTERM")
  api.close()
  setTimeout(() => rmSync(tempDir, { recursive: true, force: true }), 1000).unref()
}

process.on("SIGINT", shutdown)
process.on("SIGTERM", shutdown)
consoleProcess.on("exit", (code) => {
  shutdown()
  process.exitCode = code ?? 1
})
