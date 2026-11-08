import { defineEventHandler, setResponseHeader, setResponseStatus } from "h3"

import { probeOperatorReady } from "../utils/operator/ready"

/**
 * Console readiness.
 *
 * Without a server-only internal API origin this is a pure liveness answer for
 * the console process. With one, it also probes the operator API's `/health`
 * without credentials. The internal origin and any upstream body stay
 * server-side; the response carries only the two status words.
 */
export default defineEventHandler(async (event) => {
  const config = useRuntimeConfig(event)
  const internalOrigin =
    process.env.IBEX_OPERATOR_API_INTERNAL_ORIGIN?.trim() ||
    String(config.operatorApiInternalOrigin ?? "").trim()

  const result = await probeOperatorReady({
    internalOrigin,
    fetch: globalThis.fetch,
  })

  setResponseHeader(event, "Cache-Control", "no-store")
  if (result.status !== "ok") setResponseStatus(event, 503)
  return result
})
