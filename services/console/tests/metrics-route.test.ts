import { IncomingMessage, ServerResponse } from "node:http"
import { Socket } from "node:net"

import { createEvent } from "h3"
import { describe, expect, it } from "vitest"

import handler from "../server/routes/metrics.get"

function fakeEvent() {
  const req = new IncomingMessage(new Socket())
  const res = new ServerResponse(req)
  return { event: createEvent(req, res), res }
}

describe("console /metrics", () => {
  it("returns Prometheus text exposition with process and runtime metrics", async () => {
    const { event, res } = fakeEvent()

    const body = await handler(event)

    expect(res.getHeader("content-type")).toContain("text/plain")
    expect(res.getHeader("cache-control")).toBe("no-store")
    expect(typeof body).toBe("string")
    expect(body).toContain("# HELP")
    expect(body).toContain("process_cpu_user_seconds_total")
    expect(body).toContain("nodejs_eventloop_lag_seconds")
  })

  it("keeps the registry registered once across repeated requests", async () => {
    // A per-request collectDefaultMetrics() would throw "Already registered" on
    // the second call; the module-scope guard must keep both requests working.
    await expect(handler(fakeEvent().event)).resolves.toBeTypeOf("string")
    await expect(handler(fakeEvent().event)).resolves.toBeTypeOf("string")
  })

  it("exports no tenant or request-derived data", async () => {
    const body = await handler(fakeEvent().event)

    expect(body).not.toMatch(/org_id|orgId|tenant|request_id|session_id/)
    // Default collectors label by runtime build only (bounded cardinality).
    expect(body).toContain('nodejs_version_info{version="')
  })
})
