import { defineEventHandler, setResponseHeader } from "h3"
import { collectDefaultMetrics, register } from "prom-client"

/**
 * Console metrics (Prometheus text exposition).
 *
 * Process and Node runtime metrics only: CPU, memory, event-loop lag, GC, open
 * handles. No tenant data is read or exported, and no label is derived from a
 * request, so cardinality is bounded by the runtime itself. The registry is
 * shared per process; Nitro re-imports route modules on reload, and a second
 * `collectDefaultMetrics()` call throws "Already registered", so registration is
 * guarded on `globalThis`.
 */
const globalWithFlag = globalThis as typeof globalThis & {
  __ibexConsoleMetricsRegistered?: boolean
}

if (!globalWithFlag.__ibexConsoleMetricsRegistered) {
  collectDefaultMetrics()
  globalWithFlag.__ibexConsoleMetricsRegistered = true
}

export default defineEventHandler(async (event) => {
  setResponseHeader(event, "Content-Type", register.contentType)
  setResponseHeader(event, "Cache-Control", "no-store")
  return await register.metrics()
})
