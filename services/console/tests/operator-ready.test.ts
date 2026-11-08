import { describe, expect, it, vi } from "vitest"

import {
  probeOperatorReady,
  type ReadyFetch,
  type ReadyProbeResponse,
} from "../server/utils/operator/ready"

const INTERNAL_ORIGIN = "http://operator-api.internal:8010"

function respond(status: number): ReadyFetch {
  return async () => ({ ok: status >= 200 && status < 300, status })
}

describe("console readiness probe", () => {
  it("reports the console as serving when no internal origin is configured", async () => {
    const fetchFn = vi.fn<ReadyFetch>()

    await expect(
      probeOperatorReady({ internalOrigin: "", fetch: fetchFn }),
    ).resolves.toEqual({ status: "ok", upstream: "unchecked" })
    await expect(
      probeOperatorReady({ internalOrigin: "   ", fetch: fetchFn }),
    ).resolves.toEqual({ status: "ok", upstream: "unchecked" })
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it("reports upstream ok on a 2xx health response", async () => {
    const fetchFn = vi.fn<ReadyFetch>(async () => ({ ok: true, status: 200 }))

    await expect(
      probeOperatorReady({ internalOrigin: INTERNAL_ORIGIN, fetch: fetchFn }),
    ).resolves.toEqual({ status: "ok", upstream: "ok" })

    const [target, init] = fetchFn.mock.calls[0]!
    expect(target.toString()).toBe(`${INTERNAL_ORIGIN}/health`)
    expect(init).toMatchObject({
      method: "GET",
      cache: "no-store",
      redirect: "error",
      credentials: "omit",
    })
    expect(init).not.toHaveProperty("headers")
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it("reports upstream unavailable on a non-2xx response", async () => {
    const fetchFn = vi.fn<ReadyFetch>(respond(503))

    await expect(
      probeOperatorReady({ internalOrigin: INTERNAL_ORIGIN, fetch: fetchFn }),
    ).resolves.toEqual({ status: "degraded", upstream: "unavailable" })
  })

  it("reports upstream unavailable on a network error", async () => {
    const fetchFn: ReadyFetch = async () => {
      throw new TypeError("fetch failed")
    }

    await expect(
      probeOperatorReady({ internalOrigin: INTERNAL_ORIGIN, fetch: fetchFn }),
    ).resolves.toEqual({ status: "degraded", upstream: "unavailable" })
  })

  it("reports upstream unavailable when the probe times out", async () => {
    const timeoutFetch: ReadyFetch = (_input, init) =>
      new Promise<ReadyProbeResponse>((_resolve, reject) => {
        init.signal.addEventListener(
          "abort",
          () => reject(new DOMException("The operation timed out.", "TimeoutError")),
          { once: true },
        )
      })

    await expect(
      probeOperatorReady({
        internalOrigin: INTERNAL_ORIGIN,
        fetch: timeoutFetch,
        timeoutMs: 5,
      }),
    ).resolves.toEqual({ status: "degraded", upstream: "unavailable" })
  })

  it("treats an invalid internal origin as unavailable without calling fetch", async () => {
    const fetchFn = vi.fn<ReadyFetch>()

    await expect(
      probeOperatorReady({ internalOrigin: "not a url", fetch: fetchFn }),
    ).resolves.toEqual({ status: "degraded", upstream: "unavailable" })
    await expect(
      probeOperatorReady({
        internalOrigin: "http://user:pass@operator-api.internal:8010",
        fetch: fetchFn,
      }),
    ).resolves.toEqual({ status: "degraded", upstream: "unavailable" })
    expect(fetchFn).not.toHaveBeenCalled()
  })

  it("keeps a configured base path and drops any query or fragment", async () => {
    const fetchFn = vi.fn<ReadyFetch>(async () => ({ ok: true, status: 204 }))

    await probeOperatorReady({
      internalOrigin: "https://operator-api.internal/internal/?trace=1#fragment",
      fetch: fetchFn,
    })

    expect(fetchFn.mock.calls[0]![0].toString()).toBe(
      "https://operator-api.internal/internal/health",
    )
  })
})
