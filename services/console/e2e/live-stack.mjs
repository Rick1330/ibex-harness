import { execFileSync, spawn } from "node:child_process"
import { createServer } from "node:https"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
import { dirname, join } from "node:path"
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
const requests = []
let eventStreams = 0
let closing = false
let consoleProcess

execFileSync("/usr/bin/openssl", [
  "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
  "-keyout", keyPath, "-out", certPath, "-subj", "/CN=127.0.0.1",
  "-addext", "subjectAltName=IP:127.0.0.1,DNS:localhost",
  "-addext", "basicConstraints=critical,CA:TRUE",
], { stdio: "ignore" })

const api = createServer(
  { key: readFileSync(keyPath), cert: readFileSync(certPath) },
  (request, response) => {
    const url = new URL(request.url ?? "/", `https://127.0.0.1:${apiPort}`)
    if (url.pathname === "/__test/requests") {
      response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" })
      response.end(JSON.stringify(requests))
      return
    }
    if (url.pathname === "/__test/reset" && request.method === "POST") {
      requests.length = 0
      response.writeHead(204, { "cache-control": "no-store" })
      response.end()
      return
    }

    const cookie = request.headers.cookie ?? ""
    const cookieNames = cookie
      .split(";")
      .map((part) => part.trim().split("=", 1)[0])
      .filter(Boolean)
    requests.push({
      method: request.method,
      path: url.pathname,
      cookieNames,
      lastEventId: request.headers["last-event-id"] ?? null,
    })

    if (url.pathname === "/v1/operator/events/stream") {
      if (cookie !== sessionCookie) {
        response.writeHead(401, { "content-type": "application/json" })
        response.end(JSON.stringify({ error: { code: "INVALID_SESSION", message: "Session required" } }))
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
      } else {
        const heartbeat = setInterval(() => response.write(": heartbeat\n\n"), 15_000)
        response.on("close", () => clearInterval(heartbeat))
      }
      return
    }

    if (cookie !== sessionCookie) {
      response.writeHead(401, { "content-type": "application/json", "cache-control": "no-store" })
      response.end(JSON.stringify({ error: { code: "INVALID_SESSION", message: "Session required" } }))
      return
    }

    const body = {
      "/v1/operator/context": {
        schema_version: "operator.context.v1",
        org_id: orgId,
        role: "admin",
        org_name: "Live Workspace",
        org_slug: "live-workspace",
        org_status: "active",
        observed_at: observedAt,
      },
      "/v1/operator/overview": {
        schema_version: "operator.overview.v1",
        org_id: orgId,
        org_name: "Live Workspace",
        org_slug: "live-workspace",
        org_status: "active",
        counts: { active_users: 7, agents: 3, active_agents: 2 },
        observed_at: observedAt,
        completeness: "complete",
      },
      "/v1/operator/platform/health": {
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
    }[url.pathname]

    if (!body) {
      response.writeHead(404, { "content-type": "application/json" })
      response.end(JSON.stringify({ error: { code: "NOT_FOUND", message: "Not found" } }))
      return
    }
    response.writeHead(200, { "content-type": "application/json", "cache-control": "no-store" })
    response.end(JSON.stringify(body))
  },
)

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
