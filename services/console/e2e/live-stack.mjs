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
  return {
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
  if (pathname === "/v1/operator/context") return bodies.context
  if (pathname === "/v1/operator/overview") return bodies.overview
  if (pathname === "/v1/operator/platform/health") return bodies.health
  if (pathname === "/v1/operator/traces") return bodies.traces
  if (pathname === `/v1/operator/traces/runs/${runId}`) return bodies.traceDetail
  if (pathname === "/v1/operator/traces/trace-live-1") return bodies.traces
  if (pathname.startsWith("/v1/operator/traces/")) return "trace-missing"
  return null
}

function handleAuthenticatedJson(pathname, response) {
  const body = resolveFixtureBody(pathname)
  if (body === "trace-missing") {
    writeJson(response, 404, { error: { code: "NOT_FOUND", message: "Trace not found" } })
    return
  }
  if (!body) {
    writeJson(response, 404, { error: { code: "NOT_FOUND", message: "Not found" } })
    return
  }
  writeJson(response, 200, body)
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
  process.execPath,
  [
    join(consoleDir, "node_modules/next/dist/bin/next"),
    "dev", "--hostname", "127.0.0.1", "--port", String(consolePort),
    "--experimental-https", "--experimental-https-key", keyPath,
    "--experimental-https-cert", certPath,
  ],
  {
    cwd: consoleDir,
    env: {
      ...process.env,
      NODE_EXTRA_CA_CERTS: certPath,
      NODE_OPTIONS: `${process.env.NODE_OPTIONS ?? ""} --use-openssl-ca`.trim(),
      SSL_CERT_FILE: certPath,
      CONSOLE_DATA_MODE: "live",
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
