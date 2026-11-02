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
const sessionCookie = "ibex_session=fixture-access-secret"
const orgId = "bfc3f97b-7a61-498d-9faa-96f34fbd4f2f"
const observedAt = "2026-09-26T17:00:00Z"
const runId = "11111111-1111-4111-8111-111111111111"
const agentId = "33333333-3333-4333-8333-333333333333"
const memoryId = "44444444-4444-4444-8444-444444444444"
const sessionId = "88888888-8888-4888-8888-888888888888"
const requests = []
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

function writeJson(response, status, body, extraHeaders = {}) {
  response.writeHead(status, {
    "content-type": "application/json",
    "cache-control": "no-store",
    ...extraHeaders,
  })
  response.end(JSON.stringify(body))
}

function writeUnauthorized(response) {
  writeJson(response, 401, { error: { code: "INVALID_SESSION", message: "Session required" } })
}

function handleTestRoute(url, request, response) {
  if (url.pathname === "/__test/login") {
    response.writeHead(200, {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "set-cookie": `${sessionCookie}; Path=/; Secure; SameSite=Lax`,
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
    response.writeHead(204, { "cache-control": "no-store" })
    response.end()
    return true
  }
  return false
}

function recordRequest(request, pathname) {
  const cookie = request.headers.cookie ?? ""
  const cookieNames = cookie
    .split(";")
    .map((part) => part.trim().split("=", 1)[0])
    .filter(Boolean)
  requests.push({
    method: request.method,
    path: pathname,
    cookieNames,
    lastEventId: request.headers["last-event-id"] ?? null,
  })
  return cookie
}

function handleEventStream(cookie, response) {
  if (cookie !== sessionCookie) {
    writeUnauthorized(response)
    return
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

function fixtureBodies() {
  const traceItem = {
    trace_id: "trace-live-1",
    run_id: runId,
    request_id: "request-live-1",
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
    id: agentId,
    slug: "support-agent",
    name: "Support Agent",
    description: "Answers customer questions from the memory store.",
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
    id: memoryId,
    agent_id: agentId,
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
    lineage: {
      superseded_by: null,
      merged_into: null,
      tip: memoryId,
      replaces: [],
      replaced_by: [],
      edges_truncated: false,
    },
  }
  const sessionTurn = {
    id: "99999999-9999-4999-8999-999999999999",
    turn_index: 0,
    request_id: "req-live-1",
    input_tokens: 10,
    output_tokens: 20,
    model: "gpt-4.1",
    provider: "openai",
    latency_ms: 100,
    is_streaming: false,
    is_complete: true,
    created_at: observedAt,
    trace: {
      trace_id: "trace-live-1",
      run_id: runId,
      completeness: "complete",
      status: "ok",
      error_code: null,
      started_at: observedAt,
      ended_at: observedAt,
    },
  }
  const session = {
    id: sessionId,
    agent_id: agentId,
    external_id: "ext-live-1",
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
      org_id: orgId,
      role: "admin",
      org_name: "Live Workspace",
      org_slug: "live-workspace",
      org_status: "active",
      observed_at: observedAt,
    },
    overview: {
      schema_version: "operator.overview.v1",
      org_id: orgId,
      org_name: "Live Workspace",
      org_slug: "live-workspace",
      org_status: "active",
      counts: { active_users: 7, agents: 3, active_agents: 2 },
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

function resolveFixtureBody(pathname) {
  const bodies = fixtureBodies()
  if (pathname === "/v1/operator/sessions") return { status: 200, payload: bodies.sessions }
  if (pathname === `/v1/operator/sessions/${sessionId}`) {
    return { status: 200, payload: bodies.sessionDetail }
  }
  if (pathname.startsWith("/v1/operator/sessions/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Session not found" } } }
  }
  if (pathname === "/v1/operator/memories") return { status: 200, payload: bodies.memories }
  if (pathname === `/v1/operator/memories/${memoryId}`) {
    return { status: 200, payload: bodies.memory }
  }
  if (pathname.startsWith("/v1/operator/memories/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Memory not found" } } }
  }
  if (pathname === "/v1/operator/agents") return { status: 200, payload: bodies.agents }
  if (pathname === `/v1/operator/agents/${agentId}`) {
    return { status: 200, payload: bodies.agent }
  }
  if (pathname.startsWith("/v1/operator/agents/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Agent not found" } } }
  }
  if (pathname === "/v1/operator/context") return { status: 200, payload: bodies.context }
  if (pathname === "/v1/operator/overview") return { status: 200, payload: bodies.overview }
  if (pathname === "/v1/operator/platform/health") return { status: 200, payload: bodies.health }
  if (pathname === "/v1/operator/traces") return { status: 200, payload: bodies.traces }
  if (pathname === `/v1/operator/traces/runs/${runId}`) {
    return { status: 200, payload: bodies.traceDetail }
  }
  if (pathname === "/v1/operator/traces/trace-live-1") return { status: 200, payload: bodies.traces }
  if (pathname.startsWith("/v1/operator/traces/")) {
    return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Trace not found" } } }
  }
  return { status: 404, payload: { error: { code: "NOT_FOUND", message: "Not found" } } }
}

function handleAuthenticatedJson(pathname, response) {
  const resolved = resolveFixtureBody(pathname)
  writeJson(response, resolved.status, resolved.payload)
}

function handleApiRequest(request, response) {
  const url = new URL(request.url ?? "/", `https://127.0.0.1:${apiPort}`)
  if (handleTestRoute(url, request, response)) return

  const cookie = recordRequest(request, url.pathname)
  if (url.pathname === "/v1/operator/events/stream") {
    handleEventStream(cookie, response)
    return
  }
  if (cookie !== sessionCookie) {
    writeUnauthorized(response)
    return
  }
  handleAuthenticatedJson(url.pathname, response)
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

const api = createServer({ key: tlsKey, cert: tlsCert }, handleApiRequest)
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
