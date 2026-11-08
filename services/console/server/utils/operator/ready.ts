/**
 * Server-only readiness probe for the console.
 *
 * `/ready` answers "is this console process serving?" and, when an internal
 * API origin is configured, "can it reach the operator API's own health
 * endpoint?". The probe is deliberately credential-free: it must never carry
 * an operator session cookie or the edge operator origin. The internal origin
 * never appears in a response or in the browser bundle.
 */

export interface ReadyProbeResponse {
  ok: boolean
  status: number
}

export type ReadyFetch = (
  input: URL,
  init: {
    method: "GET"
    cache: "no-store"
    redirect: "error"
    credentials: "omit"
    signal: AbortSignal
  },
) => Promise<ReadyProbeResponse>

export interface ReadyProbeOptions {
  /** Internal API origin (server-only). Empty means "not configured". */
  internalOrigin: string
  fetch: ReadyFetch
  timeoutMs?: number
}

export type ReadyProbeResult =
  | { status: "ok"; upstream: "unchecked" | "ok" }
  | { status: "degraded"; upstream: "unavailable" }

const DEFAULT_TIMEOUT_MS = 2_000

function healthTarget(internalOrigin: string): URL | null {
  let base: URL
  try {
    base = new URL(internalOrigin)
  } catch {
    return null
  }
  if (base.protocol !== "http:" && base.protocol !== "https:") return null
  if (base.username || base.password) return null
  base.pathname = `${base.pathname.replace(/\/+$/, "")}/health`
  base.search = ""
  base.hash = ""
  return base
}

/**
 * Probe readiness.
 *
 * - No internal origin: `ok` / `unchecked` — the console itself is serving.
 * - 2xx health: `ok` / `ok`.
 * - Anything else (timeout, network error, non-2xx, invalid origin):
 *   `degraded` / `unavailable`.
 */
export async function probeOperatorReady({
  internalOrigin,
  fetch,
  timeoutMs = DEFAULT_TIMEOUT_MS,
}: ReadyProbeOptions): Promise<ReadyProbeResult> {
  const raw = internalOrigin.trim()
  if (!raw) return { status: "ok", upstream: "unchecked" }

  const target = healthTarget(raw)
  if (!target) return { status: "degraded", upstream: "unavailable" }

  try {
    const response = await fetch(target, {
      method: "GET",
      cache: "no-store",
      redirect: "error",
      credentials: "omit",
      signal: AbortSignal.timeout(timeoutMs),
    })
    return response.ok
      ? { status: "ok", upstream: "ok" }
      : { status: "degraded", upstream: "unavailable" }
  } catch {
    return { status: "degraded", upstream: "unavailable" }
  }
}
