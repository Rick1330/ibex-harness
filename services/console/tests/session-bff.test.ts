import { IncomingMessage, ServerResponse } from "node:http"
import { Socket } from "node:net"

import { createEvent, type H3Event } from "h3"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import bootstrapHandler from "../server/api/operator/session/bootstrap.get"
import loginHandler from "../server/api/operator/session/login.post"
import logoutHandler from "../server/api/operator/session/logout.post"
import {
  MAX_CACHED_ROTATIONS,
  OperatorLoginRedirect,
  OperatorUpstreamError,
  appendSessionDeletionCookies,
  callOperatorSession,
  fetchOperatorJson,
  resetRotationCache,
  toHttpError,
} from "../server/utils/operator/http"

const API_ORIGIN = "https://operator-api.internal:8010"
const CONSOLE_ORIGIN = "https://console.example"

type FakeEvent = {
  event: H3Event
  req: IncomingMessage
  res: ServerResponse
}

function fakeEvent(
  init: {
    url?: string
    headers?: Record<string, string>
  } = {},
): FakeEvent {
  const req = new IncomingMessage(new Socket())
  req.url = init.url ?? "/"
  req.method = "GET"
  req.headers = { host: "console.example", ...init.headers }
  const res = new ServerResponse(req)
  return { event: createEvent(req, res), req, res }
}

function headerValue(value: string | number | string[] | undefined): string {
  if (Array.isArray(value)) return value.join("\n")
  return value === undefined ? "" : String(value)
}

function setCookieList(res: ServerResponse): string[] {
  const value = res.getHeader("set-cookie")
  if (Array.isArray(value)) return value.map(String)
  return value === undefined ? [] : [String(value)]
}

/** A POST event with a body stream, so the capped reader sees real bytes. */
function eventWithBody(init: {
  body?: string | Buffer
  headers?: Record<string, string>
  url?: string
}): FakeEvent {
  const req = new IncomingMessage(new Socket())
  req.url = init.url ?? "/api/operator/session/login"
  req.method = "POST"
  req.headers = { host: "console.example", ...init.headers }
  const res = new ServerResponse(req)
  const event = createEvent(req, res)
  if (init.body !== undefined) {
    req.push(Buffer.isBuffer(init.body) ? init.body : Buffer.from(init.body))
  }
  req.push(null)
  return { event, req, res }
}

function upstream(body: unknown, init: { status?: number; setCookie?: string[] } = {}): Response {
  const headers = new Headers({ "content-type": "application/json" })
  for (const cookie of init.setCookie ?? []) headers.append("set-cookie", cookie)
  return new Response(JSON.stringify(body), {
    status: init.status ?? 200,
    headers,
  })
}

function stubFetch(handler: (target: URL, init: RequestInit) => Response | Promise<Response>) {
  const fetchMock = vi.fn(async (input: URL | string, init?: RequestInit) =>
    handler(input instanceof URL ? input : new URL(String(input)), init ?? {}),
  )
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

/** Map a `fetchOperatorJson` rejection the way a BFF route does. */
async function mappedHttpError(run: () => Promise<unknown>): Promise<unknown> {
  try {
    await run()
  } catch (error) {
    try {
      toHttpError(error)
    } catch (mapped) {
      return mapped
    }
  }
  return undefined
}

beforeEach(() => {
  vi.stubEnv("IBEX_OPERATOR_API_ORIGIN", API_ORIGIN)
  vi.stubGlobal("useRuntimeConfig", () => ({ operatorApiOrigin: "" }))
  // A rotation is retained per refresh-token hash for 10s of wall-clock time.
  // Without this reset, a case that rotates would serve its access value to the
  // next case that reuses the same token.
  resetRotationCache()
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.unstubAllEnvs()
})

describe("BFF session cookie relay", () => {
  it("relays the API Set-Cookie headers to the Console origin on login", async () => {
    const { event, res } = fakeEvent({ headers: { "x-csrf-token": "csrf-value", origin: CONSOLE_ORIGIN } })
    const fetchMock = stubFetch((target) => {
      expect(target.origin).toBe(API_ORIGIN)
      expect(target.pathname).toBe("/v1/operator/session/login")
      return upstream(
        { status: "ok", provisional: false, org_id: "org-1", csrf_token: "csrf-value", warning: "internal" },
        {
          setCookie: [
            "ibex_session=access-token; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=3600",
            "ibex_refresh=refresh-token; Path=/; HttpOnly; Secure; SameSite=Lax",
            "ibex_csrf=csrf-value; Path=/; Secure; SameSite=Lax",
          ],
        },
      )
    })

    const payload = await callOperatorSession(event, "login", { pat: "ibex_pat_123456789" })

    const [target, init] = fetchMock.mock.calls[0]!
    expect(String(target)).toBe(`${API_ORIGIN}/v1/operator/session/login`)
    expect((init.headers as Headers).get("x-csrf-token")).toBe("csrf-value")
    expect((init.headers as Headers).get("origin")).toBe(CONSOLE_ORIGIN)
    expect(JSON.parse(String(init.body))).toEqual({ pat: "ibex_pat_123456789" })

    const relayed = headerValue(res.getHeader("set-cookie"))
    expect(relayed).toContain("ibex_session=access-token")
    expect(relayed).toContain("HttpOnly")
    expect(relayed).toContain("ibex_refresh=refresh-token")
    expect(relayed).toContain("ibex_csrf=csrf-value")

    // Only the browser-facing fields survive; the PAT and internal warning do not.
    expect(payload).toEqual({
      status: "ok",
      provisional: false,
      org_id: "org-1",
      csrf_token: "csrf-value",
    })
    expect(JSON.stringify(payload)).not.toContain("ibex_pat_")
    expect(JSON.stringify(payload)).not.toContain("warning")
  })

  it("forwards the refresh and CSRF cookies plus the CSRF header on logout", async () => {
    const { event, res } = fakeEvent({
      url: "/logout",
      headers: {
        cookie: "ibex_session=access-token; ibex_refresh=refresh-token; ibex_csrf=csrf-value",
        "x-csrf-token": "csrf-value",
        origin: CONSOLE_ORIGIN,
      },
    })
    const fetchMock = stubFetch(() =>
      upstream(
        { status: "ok" },
        {
          setCookie: [
            "ibex_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0",
            "ibex_refresh=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0",
            "ibex_csrf=; Path=/; Secure; SameSite=Lax; Max-Age=0",
          ],
        },
      ),
    )

    await callOperatorSession(event, "logout")

    const [, init] = fetchMock.mock.calls[0]!
    const cookie = (init.headers as Headers).get("cookie") ?? ""
    expect(cookie).toContain("ibex_session=access-token")
    expect(cookie).toContain("ibex_refresh=refresh-token")
    expect(cookie).toContain("ibex_csrf=csrf-value")
    expect((init.headers as Headers).get("x-csrf-token")).toBe("csrf-value")

    const relayed = headerValue(res.getHeader("set-cookie"))
    expect(relayed).toContain("ibex_session=;")
    expect(relayed).toContain("ibex_refresh=;")
    expect(relayed).toContain("Max-Age=0")
  })

  it("clears cookies before reporting an invalid-session logout", async () => {
    const { event, res } = fakeEvent({
      url: "/logout",
      headers: { cookie: "ibex_session=stale; ibex_csrf=csrf-value", "x-csrf-token": "csrf-value" },
    })
    stubFetch(() =>
      upstream(
        { error: { code: "INVALID_TOKEN", message: "invalid session" } },
        {
          status: 401,
          setCookie: ["ibex_session=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0"],
        },
      ),
    )

    await expect(callOperatorSession(event, "logout")).rejects.toBeInstanceOf(OperatorUpstreamError)
    expect(headerValue(res.getHeader("set-cookie"))).toContain("ibex_session=;")
  })

  it("turns a 401 login into a stable message, not the upstream detail", () => {
    const upstreamError = new OperatorUpstreamError(401, "INVALID_TOKEN", "invalid token")

    let thrown: unknown
    try {
      toHttpError(upstreamError, { login: true })
    } catch (error) {
      thrown = error
    }

    expect(thrown).toMatchObject({
      statusCode: 401,
      data: { error: { code: "INVALID_TOKEN", message: "That personal access token was not accepted." } },
    })
  })
})

describe("BFF 401 page-load handling", () => {
  it("redirects a document request to /login with the original path", async () => {
    const { event, res } = fakeEvent({
      url: "/explore?limit=10",
      headers: { accept: "text/html,application/xhtml+xml" },
    })
    stubFetch(() => upstream({ error: { code: "INVALID_SESSION", message: "Session required" } }, { status: 401 }))

    await expect(
      fetchOperatorJson(event, "traces", (value) => value),
    ).rejects.toBeInstanceOf(OperatorLoginRedirect)

    expect(res.statusCode).toBe(302)
    expect(headerValue(res.getHeader("location"))).toBe(
      `/login?next=${encodeURIComponent("/explore?limit=10")}`,
    )
  })

  it("returns 401 to a data fetch without refreshing when there is no refresh cookie", async () => {
    // Fail closed: no data and no invented payload. With nothing to rotate, the
    // API must not be asked to refresh. A data caller gets 401 rather than a
    // redirect, because a followed redirect would hand it the login page as a
    // 200 body and `useAsyncData` would store that HTML as operator data.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "application/json", cookie: "ibex_session=expired" },
    })
    const fetchMock = stubFetch(() =>
      upstream({ error: { code: "INVALID_SESSION", message: "Session required" } }, { status: 401 }),
    )

    let httpError: unknown
    try {
      await fetchOperatorJson(event, "overview", (value) => value)
    } catch (error) {
      try {
        toHttpError(error)
      } catch (mapped) {
        httpError = mapped
      }
    }

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(httpError).toMatchObject({
      statusCode: 401,
      data: { error: { code: "INVALID_SESSION" } },
    })
    // No redirect was written: the caller decides how to show the sign-in state.
    expect(res.getHeader("location")).toBeUndefined()
  })

  it("returns 401 to an internal data read that carries no Accept header", async () => {
    // Nitro's `event.fetch` does not forward the outer document's Accept (h3
    // drops it in `getProxyRequestHeaders`), so an SSR data read arrives with no
    // Accept at all. It must not be mistaken for a document navigation.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: { cookie: "ibex_session=expired" },
    })
    stubFetch(() =>
      upstream({ error: { code: "INVALID_SESSION", message: "Session required" } }, { status: 401 }),
    )

    const httpError = await mappedHttpError(() =>
      fetchOperatorJson(event, "overview", (value) => value),
    )

    expect(httpError).toMatchObject({ statusCode: 401 })
    expect(res.getHeader("location")).toBeUndefined()
  })

  it("returns 401 to a non-GET request even when it accepts HTML", async () => {
    // Only a GET document navigation is redirected; a POST that accepts HTML is
    // still a data caller and must see the status, not a followed login page.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "text/html", cookie: "ibex_session=expired" },
    })
    event.node.req.method = "POST"
    stubFetch(() =>
      upstream({ error: { code: "INVALID_SESSION", message: "Session required" } }, { status: 401 }),
    )

    const httpError = await mappedHttpError(() =>
      fetchOperatorJson(event, "overview", (value) => value),
    )

    expect(httpError).toMatchObject({ statusCode: 401 })
    expect(res.getHeader("location")).toBeUndefined()
  })
})

describe("BFF refresh-and-retry", () => {
  it("refreshes an expired access cookie once and retries the read", async () => {
    const { event } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=refresh-token; ibex_csrf=csrf-value",
      },
    })
    const calls: Array<{ path: string; cookie: string; csrf: string }> = []
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      calls.push({
        path: target.pathname,
        cookie: headers.get("cookie") ?? "",
        csrf: headers.get("x-csrf-token") ?? "",
      })
      if (target.pathname === "/v1/operator/session/refresh") {
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: ["ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax"] },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const result = await fetchOperatorJson(event, "overview", (value) => value)

    expect(result).toEqual({ org_id: "org-1", ok: true })
    expect(calls.map((call) => call.path)).toEqual([
      "/v1/operator/overview",
      "/v1/operator/session/refresh",
      "/v1/operator/overview",
    ])
    // The retry carries the cookie the API just issued, not the expired one.
    expect(calls[2]!.cookie).toBe("ibex_session=fresh-access")
    // The server-side refresh presents the browser's CSRF cookie as the header.
    expect(calls[1]!.csrf).toBe("csrf-value")
  })

  it("supplies the Console's own origin when a server-side refresh has no Origin or Referer", async () => {
    // A data read is a GET, so it normally carries neither header. Without an
    // Origin the API's CSRF middleware answers 403 origin_failed before it looks
    // at the CSRF token, and the retry never happens.
    const { event } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=refresh-token; ibex_csrf=csrf-value",
        "x-forwarded-proto": "https",
      },
    })
    let refreshOrigin = ""
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshOrigin = headers.get("origin") ?? ""
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: ["ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax"] },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    await fetchOperatorJson(event, "overview", (value) => value)

    // Derived from the request URL behind the edge, not hard-coded.
    expect(refreshOrigin).toBe("https://console.example")
  })

  it("forwards an existing Origin unchanged on the server-side refresh", async () => {
    // The request origin here is http://console.example, so a synthesized value
    // would be visibly different from the Origin the browser actually sent.
    const { event } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=refresh-token; ibex_csrf=csrf-value",
        origin: "https://console.example",
      },
    })
    let refreshOrigin = ""
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshOrigin = headers.get("origin") ?? ""
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: ["ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax"] },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    await fetchOperatorJson(event, "overview", (value) => value)

    expect(refreshOrigin).toBe("https://console.example")
  })

  it("shares one refresh across concurrent reads instead of replaying the refresh token", async () => {
    const { event } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=single-flight-token; ibex_csrf=csrf-value",
      },
    })
    let refreshCalls = 0
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshCalls += 1
        // The API accepts a refresh token once. Model that so the test fails if
        // the rotation is not shared: a second call is refused, not honoured.
        if (refreshCalls > 1) {
          return upstream(
            { error: { code: "INVALID_TOKEN", message: "invalid refresh token" } },
            { status: 401 },
          )
        }
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: ["ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax"] },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const results = await Promise.all([
      fetchOperatorJson(event, "overview", (value) => value),
      fetchOperatorJson(event, "overview", (value) => value),
      fetchOperatorJson(event, "overview", (value) => value),
    ])

    // Three parallel 401s, one rotation. A second refresh would replay the
    // single-use token, be refused, and log the operator out mid page load.
    expect(refreshCalls).toBe(1)
    expect(results).toEqual([
      { org_id: "org-1", ok: true },
      { org_id: "org-1", ok: true },
      { org_id: "org-1", ok: true },
    ])
  })

  it("serves the settled rotation to a later read with the same refresh token (server render)", async () => {
    // Server rendering is sequential, not a race. The outer request's Cookie
    // header never changes during the render, so the second internal read still
    // presents the expired access cookie and the refresh token the first read
    // already consumed. Two `useAsyncData` calls — a layout and a page — are
    // enough to reach this.
    const cookie = "ibex_session=expired; ibex_refresh=ssr-token; ibex_csrf=csrf-value"
    const layout = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "application/json", cookie },
    })
    const page = fakeEvent({
      url: "/api/operator/context",
      headers: { accept: "application/json", cookie },
    })

    let refreshCalls = 0
    const readCookies: string[] = []
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshCalls += 1
        // The API accepts a refresh token once. A second presentation is
        // refused, which is exactly what made the second SSR read sign the
        // operator out.
        if (refreshCalls > 1) {
          return upstream(
            { error: { code: "INVALID_TOKEN", message: "refresh token already used" } },
            { status: 401 },
          )
        }
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: ["ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax"] },
        )
      }
      readCookies.push(headers.get("cookie") ?? "")
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const layoutData = await fetchOperatorJson(layout.event, "overview", (value) => value)
    const pageData = await fetchOperatorJson(page.event, "context", (value) => value)

    expect(refreshCalls).toBe(1)
    expect(layoutData).toEqual({ org_id: "org-1", ok: true })
    expect(pageData).toEqual({ org_id: "org-1", ok: true })
    // Both reads 401'd with the stale cookie and retried with the same rotated
    // value, so the single-use refresh token was presented upstream once.
    expect(readCookies).toEqual([
      "ibex_session=expired",
      "ibex_session=fresh-access",
      "ibex_session=expired",
      "ibex_session=fresh-access",
    ])
  })

  it("rotates again for a different refresh token", async () => {
    // The retained value is keyed by the refresh token, so a second session
    // must still get its own rotation rather than being served the first one.
    const first = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=token-a; ibex_csrf=csrf-value",
      },
    })
    const second = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=token-b; ibex_csrf=csrf-value",
      },
    })

    const refreshed: string[] = []
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        const presented = headers.get("cookie") ?? ""
        const token = presented.includes("token-a")
          ? "token-a"
          : presented.includes("token-b")
            ? "token-b"
            : "unknown"
        refreshed.push(token)
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: [`ibex_session=fresh-${token}; Path=/; HttpOnly; Secure; SameSite=Lax`] },
        )
      }
      const cookie = headers.get("cookie") ?? ""
      return cookie.includes("fresh-token-a") || cookie.includes("fresh-token-b")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    await fetchOperatorJson(first.event, "overview", (value) => value)
    await fetchOperatorJson(second.event, "overview", (value) => value)

    expect(refreshed).toEqual(["token-a", "token-b"])
  })

  it("stops serving the retained rotation after its TTL", async () => {
    // Fake timers, not a sleep: the TTL is wall-clock time, so the clock and the
    // eviction timer advance together.
    vi.useFakeTimers()
    const { event } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=ttl-token; ibex_csrf=csrf-value",
      },
    })

    let refreshCalls = 0
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshCalls += 1
        return upstream(
          { status: "ok", org_id: "org-1" },
          { setCookie: [`ibex_session=fresh-${refreshCalls}; Path=/; HttpOnly; Secure; SameSite=Lax`] },
        )
      }
      return headers.get("cookie")?.includes("fresh-")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    await fetchOperatorJson(event, "overview", (value) => value)
    expect(refreshCalls).toBe(1)

    // One millisecond past the 10s TTL.
    vi.advanceTimersByTime(10_001)

    // The entry is gone, so the stale refresh token is presented again and the
    // API issues a second value. A retained entry would answer from cache.
    await fetchOperatorJson(event, "overview", (value) => value)
    expect(refreshCalls).toBe(2)
  })

  it("relays the rotation to every response that uses it, including a concurrent waiter", async () => {
    // Two independent responses, not one shared event. The waiter succeeds on
    // the shared rotation *and* relays its Set-Cookie: if the initiating
    // response is cancelled or lost after the refresh succeeded, a waiter that
    // relayed nothing would leave the browser holding the expired access cookie
    // and the consumed refresh token.
    const cookie = "ibex_session=expired; ibex_refresh=shared-token; ibex_csrf=csrf-value"
    const initiator = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "application/json", cookie },
    })
    const waiter = fakeEvent({
      url: "/api/operator/context",
      headers: { accept: "application/json", cookie },
    })

    let refreshCalls = 0
    let rejections = 0
    let bothRejected!: () => void
    const bothReadsRejected = new Promise<void>((resolve) => {
      bothRejected = resolve
    })

    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshCalls += 1
        // Hold the rotation open until both reads have 401'd, so the second
        // event overlaps it instead of finding a settled entry.
        return bothReadsRejected.then(() =>
          upstream(
            { status: "ok", org_id: "org-1" },
            {
              setCookie: [
                "ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax",
                "ibex_refresh=rotated-refresh; Path=/; HttpOnly; Secure; SameSite=Lax",
              ],
            },
          ),
        )
      }
      if (headers.get("cookie")?.includes("fresh-access")) {
        return upstream({ org_id: "org-1", ok: true })
      }
      rejections += 1
      if (rejections === 2) bothRejected()
      return upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const initiatingRead = fetchOperatorJson(initiator.event, "overview", (value) => value)
    const waitingRead = fetchOperatorJson(waiter.event, "context", (value) => value)
    const [initiatingData, waitingData] = await Promise.all([initiatingRead, waitingRead])

    expect(refreshCalls).toBe(1)
    expect(initiatingData).toEqual({ org_id: "org-1", ok: true })
    expect(waitingData).toEqual({ org_id: "org-1", ok: true })

    const initiatingCookies = setCookieList(initiator.res)
    expect(initiatingCookies.find((value) => value.startsWith("ibex_session="))).toContain(
      "ibex_session=fresh-access",
    )
    expect(initiatingCookies.find((value) => value.startsWith("ibex_refresh="))).toContain(
      "ibex_refresh=rotated-refresh",
    )
    const waiterCookies = setCookieList(waiter.res)
    expect(waiterCookies.find((value) => value.startsWith("ibex_session="))).toContain(
      "ibex_session=fresh-access",
    )
    expect(waiterCookies.find((value) => value.startsWith("ibex_refresh="))).toContain(
      "ibex_refresh=rotated-refresh",
    )
  })

  it("relays the rotated cookies to a cached hit, not only the initiating response", async () => {
    // The initiating response is cancelled or lost after the refresh succeeded,
    // so the browser never received its Set-Cookie. A later read inside the
    // window is answered from the retained rotation; it must carry the cookies
    // too, otherwise the browser keeps the expired access cookie and the
    // consumed refresh token.
    const cookie = "ibex_session=expired; ibex_refresh=cached-token; ibex_csrf=csrf-value"
    const initiator = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "application/json", cookie },
    })
    const cachedHit = fakeEvent({
      url: "/api/operator/context",
      headers: { accept: "application/json", cookie },
    })

    let refreshCalls = 0
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshCalls += 1
        return upstream(
          { status: "ok", org_id: "org-1" },
          {
            setCookie: [
              "ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax",
              "ibex_refresh=rotated-refresh; Path=/; HttpOnly; Secure; SameSite=Lax",
            ],
          },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    // Sequential, not concurrent: the first rotation has settled before the
    // second read starts, so the second read is a cache hit rather than a waiter.
    await fetchOperatorJson(initiator.event, "overview", (value) => value)
    await fetchOperatorJson(cachedHit.event, "context", (value) => value)

    expect(refreshCalls).toBe(1)
    const relayed = setCookieList(cachedHit.res)
    expect(relayed.find((value) => value.startsWith("ibex_session="))).toContain(
      "ibex_session=fresh-access",
    )
    expect(relayed.find((value) => value.startsWith("ibex_refresh="))).toContain(
      "ibex_refresh=rotated-refresh",
    )
  })

  it("never evicts an in-flight rotation when the map is at capacity", async () => {
    // Fill the cache past its cap while every rotation is still pending. An
    // eviction that dropped a pending entry would let a later read miss the
    // cache and present the same single-use refresh token again — which the API
    // treats as reuse and answers by revoking the whole session family.
    const total = MAX_CACHED_ROTATIONS + 1
    const releases: Array<() => void> = []
    const refreshCounts = new Map<string, number>()
    // The first pass holds every rotation open. The replay pass answers a
    // refresh immediately, so a token that was evicted is counted and the test
    // fails on the assertion below instead of hanging on an unreleased fetch.
    let replaying = false

    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        const presented = headers.get("cookie") ?? ""
        const token = /ibex_refresh=([^;]+)/.exec(presented)?.[1] ?? "unknown"
        refreshCounts.set(token, (refreshCounts.get(token) ?? 0) + 1)
        const rotated = upstream(
          { status: "ok", org_id: "org-1" },
          {
            setCookie: [
              `ibex_session=fresh-${token}; Path=/; HttpOnly; Secure; SameSite=Lax`,
            ],
          },
        )
        if (replaying) return rotated
        return new Promise<Response>((resolve) => {
          releases.push(() => resolve(rotated))
        })
      }
      return headers.get("cookie")?.includes("fresh-")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const events = Array.from({ length: total }, (_, index) =>
      fakeEvent({
        url: "/api/operator/overview",
        headers: {
          accept: "application/json",
          cookie: `ibex_session=expired; ibex_refresh=cap-token-${index}; ibex_csrf=csrf-value`,
        },
      }),
    )

    const reads = events.map(({ event }) => fetchOperatorJson(event, "overview", (value) => value))
    // Every read has 401'd and started its own rotation; none has settled, so
    // the map is over its cap with nothing that may legally be evicted.
    await vi.waitFor(() => expect(releases).toHaveLength(total))

    for (const release of releases) release()
    await Promise.all(reads)

    // Each token must still be cached: a second read for any of them may not
    // present its refresh token upstream again.
    replaying = true
    await Promise.all(
      events.map(({ event }) => fetchOperatorJson(event, "overview", (value) => value)),
    )
    expect(refreshCounts.size).toBe(total)
    expect(Math.max(...refreshCounts.values())).toBe(1)
  })

  it("fails every concurrent waiter when the shared rotation is refused", async () => {
    const { event } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=shared-failure-token; ibex_csrf=csrf-value",
      },
    })
    let refreshCalls = 0
    stubFetch((target) => {
      if (target.pathname === "/v1/operator/session/refresh") {
        refreshCalls += 1
        return upstream({ error: { code: "INVALID_TOKEN", message: "invalid refresh token" } }, { status: 401 })
      }
      return upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const outcomes = await Promise.allSettled([
      fetchOperatorJson(event, "overview", (value) => value),
      fetchOperatorJson(event, "overview", (value) => value),
      fetchOperatorJson(event, "overview", (value) => value),
    ])

    expect(refreshCalls).toBe(1)
    for (const outcome of outcomes) {
      expect(outcome.status).toBe("rejected")
      if (outcome.status === "rejected") {
        expect(outcome.reason).toMatchObject({ status: 401, code: "INVALID_SESSION" })
      }
    }
  })

  it("returns 401 to a data request when the refresh is refused", async () => {
    const { event, res } = fakeEvent({
      url: "/api/operator/overview?tab=1",
      headers: { accept: "application/json", cookie: "ibex_session=expired; ibex_refresh=stale" },
    })
    const fetchMock = stubFetch((target) =>
      target.pathname === "/v1/operator/session/refresh"
        ? upstream({ error: { code: "INVALID_TOKEN", message: "invalid refresh token" } }, { status: 401 })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 }),
    )

    await expect(fetchOperatorJson(event, "overview", (value) => value)).rejects.toMatchObject({
      status: 401,
      code: "INVALID_SESSION",
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(res.getHeader("location")).toBeUndefined()
  })

  it("relays the rotated cookies to the event it renders during a server-side refresh", async () => {
    // The refresh is a direct upstream fetch, so its Set-Cookie reaches this
    // event. This is the half of the contract `http.ts` owns; an SSR caller
    // that reaches the route through `event.$fetch` drops the headers one
    // layer up, which is why that path must not be reintroduced here.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=refresh-token; ibex_csrf=csrf-value",
      },
    })
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        return upstream(
          { status: "ok", org_id: "org-1" },
          {
            setCookie: [
              "ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax",
              "ibex_refresh=rotated-refresh; Path=/; HttpOnly; Secure; SameSite=Lax",
            ],
          },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    const result = await fetchOperatorJson(event, "overview", (value) => value)

    expect(result).toEqual({ org_id: "org-1", ok: true })
    const cookies = setCookieList(res)
    expect(cookies.find((cookie) => cookie.startsWith("ibex_session="))).toContain(
      "ibex_session=fresh-access",
    )
    // The rotated refresh token is relayed too, so a rotating token stays in
    // step with the browser instead of being replayed from the stale copy.
    expect(cookies.find((cookie) => cookie.startsWith("ibex_refresh="))).toContain(
      "ibex_refresh=rotated-refresh",
    )
  })

  it("appends each rotated cookie exactly once", async () => {
    // A second relay (for example `rotateAccessCookie` and a route handler both
    // forwarding) would emit duplicate Set-Cookie headers for the same name and
    // leave the browser's choice between them undefined.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: {
        accept: "application/json",
        cookie: "ibex_session=expired; ibex_refresh=refresh-token; ibex_csrf=csrf-value",
      },
    })
    stubFetch((target, init) => {
      const headers = new Headers(init.headers)
      if (target.pathname === "/v1/operator/session/refresh") {
        return upstream(
          { status: "ok", org_id: "org-1" },
          {
            setCookie: [
              "ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax",
              "ibex_refresh=rotated-refresh; Path=/; HttpOnly; Secure; SameSite=Lax",
            ],
          },
        )
      }
      return headers.get("cookie")?.includes("fresh-access")
        ? upstream({ org_id: "org-1", ok: true })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 })
    })

    await fetchOperatorJson(event, "overview", (value) => value)

    const names = setCookieList(res).map((cookie) => cookie.split("=", 1)[0])
    expect(names.filter((name) => name === "ibex_session")).toHaveLength(1)
    expect(names.filter((name) => name === "ibex_refresh")).toHaveLength(1)
  })

  it("writes no Set-Cookie header when the refresh returns none", async () => {
    // An unconditional append would emit an empty header. With no rotated
    // access value the read must still fail closed with a 401.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "application/json", cookie: "ibex_session=expired; ibex_refresh=refresh-token" },
    })
    stubFetch((target) =>
      target.pathname === "/v1/operator/session/refresh"
        ? upstream({ status: "ok" })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 }),
    )

    await expect(fetchOperatorJson(event, "overview", (value) => value)).rejects.toMatchObject({
      status: 401,
      code: "INVALID_SESSION",
    })

    expect(res.getHeader("set-cookie")).toBeUndefined()
    expect(setCookieList(res)).toHaveLength(0)
  })

  it("stops after one retry when the refreshed session is still rejected", async () => {
    // A second 401 must not trigger a second refresh: the retry flag is the
    // recursion guard, and the data read still fails closed with a 401.
    const { event, res } = fakeEvent({
      headers: { accept: "application/json", cookie: "ibex_session=expired; ibex_refresh=refresh-token" },
    })
    const fetchMock = stubFetch((target) =>
      target.pathname === "/v1/operator/session/refresh"
        ? upstream(
            { status: "ok" },
            { setCookie: ["ibex_session=fresh-access; Path=/; HttpOnly; Secure; SameSite=Lax"] },
          )
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 }),
    )

    await expect(fetchOperatorJson(event, "overview", (value) => value)).rejects.toMatchObject({
      status: 401,
      code: "INVALID_SESSION",
    })

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(res.getHeader("location")).toBeUndefined()
  })
})

describe("session bootstrap", () => {
  it("returns the configured CSRF cookie name and this browser's token", () => {
    // The logout page must not hard-code `ibex_csrf`: a deployment that renames
    // the cookie would otherwise send no X-CSRF-Token and never revoke.
    vi.stubEnv("IBEX_OPERATOR_CSRF_COOKIE_NAME", "acme_csrf")
    const { event } = fakeEvent({ headers: { cookie: "acme_csrf=csrf-value" } })

    expect(bootstrapHandler(event)).toEqual({
      csrf_cookie_name: "acme_csrf",
      csrf_token: "csrf-value",
    })
  })

  it("returns a null token when the browser has no CSRF cookie", () => {
    vi.stubEnv("IBEX_OPERATOR_CSRF_COOKIE_NAME", "acme_csrf")
    const { event } = fakeEvent({ headers: { cookie: "ibex_csrf=csrf-value" } })

    expect(bootstrapHandler(event)).toEqual({
      csrf_cookie_name: "acme_csrf",
      csrf_token: null,
    })
  })
})

describe("login body guard", () => {
  it("rejects an absent Content-Length by design, before reading the body", async () => {
    // A chunked request can omit the header entirely. The header check refuses
    // that shape rather than reading an unbounded stream, so this test covers
    // the header policy and never reaches the byte counter below.
    const { event } = eventWithBody({
      body: `{"pat":"${"x".repeat(9_000)}"}`,
      headers: { "content-type": "application/json" },
    })

    await expect(loginHandler(event)).rejects.toMatchObject({
      statusCode: 413,
      data: { error: { code: "PAYLOAD_TOO_LARGE" } },
    })
  })

  it("rejects a body larger than its declared Content-Length (the capped reader)", async () => {
    // The declared length passes the header check, so only the byte counter in
    // `readCappedRawBody` can produce this 413. Remove that reader and the 9000
    // bytes parse as JSON, the PAT length check answers 400, and this fails.
    const { event } = eventWithBody({
      body: `{"pat":"${"x".repeat(9_000)}"}`,
      headers: { "content-type": "application/json", "content-length": "10" },
    })

    await expect(loginHandler(event)).rejects.toMatchObject({
      statusCode: 413,
      data: { error: { code: "PAYLOAD_TOO_LARGE" } },
    })
  })

  it("rejects a non-JSON content type with 415", async () => {
    const body = JSON.stringify({ pat: "ibex_pat_123456789" })
    const { event } = eventWithBody({
      body,
      headers: { "content-type": "text/plain", "content-length": String(Buffer.byteLength(body)) },
    })

    await expect(loginHandler(event)).rejects.toMatchObject({
      statusCode: 415,
      data: { error: { code: "UNSUPPORTED_MEDIA_TYPE" } },
    })
  })

  it("rejects a form-encoded login even when Origin is absent (login CSRF)", async () => {
    // A cross-site HTML form can omit Origin but cannot send application/json
    // without a CORS preflight; the content-type check is what closes that path.
    const body = "pat=ibex_pat_123456789"
    const { event } = eventWithBody({
      body,
      headers: {
        "content-type": "application/x-www-form-urlencoded",
        "content-length": String(Buffer.byteLength(body)),
      },
    })

    await expect(loginHandler(event)).rejects.toMatchObject({ statusCode: 415 })
  })

  it("accepts a valid JSON body and forwards the PAT", async () => {
    const body = JSON.stringify({ pat: "ibex_pat_123456789" })
    const { event } = eventWithBody({
      body,
      headers: { "content-type": "application/json; charset=utf-8", "content-length": String(Buffer.byteLength(body)) },
    })
    const fetchMock = stubFetch(() =>
      upstream(
        { status: "ok", org_id: "org-1", csrf_token: "csrf-value" },
        { setCookie: ["ibex_session=access-token; Path=/; HttpOnly; Secure; SameSite=Lax"] },
      ),
    )

    const payload = await loginHandler(event)

    const [, init] = fetchMock.mock.calls[0]!
    expect(JSON.parse(String(init.body))).toEqual({ pat: "ibex_pat_123456789" })
    expect(payload).toEqual({ status: "ok", org_id: "org-1", csrf_token: "csrf-value" })
  })
})

describe("logout cookie deletion", () => {
  it("clears all three session cookies even when upstream rejects the logout", async () => {
    const { event, res } = eventWithBody({
      url: "/api/operator/session/logout",
      headers: { cookie: "ibex_session=stale; ibex_refresh=stale-refresh; ibex_csrf=stale" },
    })
    // No X-CSRF-Token header: the API's CSRF middleware answers 403 before its
    // handler runs, so it never emits a deletion cookie of its own.
    stubFetch(() => upstream({ error: { code: "CSRF_REJECTED", message: "csrf failed" } }, { status: 403 }))

    let thrown: unknown
    try {
      await logoutHandler(event)
    } catch (error) {
      thrown = error
    }

    expect(thrown).toMatchObject({
      statusCode: 403,
      data: { error: { code: "CSRF_REJECTED" } },
    })

    const cookies = setCookieList(res)
    const session = cookies.find((cookie) => cookie.startsWith("ibex_session="))
    const refresh = cookies.find((cookie) => cookie.startsWith("ibex_refresh="))
    const csrf = cookies.find((cookie) => cookie.startsWith("ibex_csrf="))

    for (const cookie of [session, refresh, csrf]) {
      expect(cookie).toBeDefined()
      expect(cookie).toContain("Max-Age=0")
      expect(cookie).toContain("Secure")
      expect(cookie).toContain("SameSite=Lax")
      expect(cookie).toContain("Path=/")
    }
    expect(session).toContain("HttpOnly")
    expect(refresh).toContain("HttpOnly")
    // The CSRF cookie is read by the client, so it must not be HttpOnly.
    expect(csrf).not.toContain("HttpOnly")
  })

  it("uses the configured Domain so a domain-scoped cookie is actually removed", () => {
    // The API issues its cookies with `DASHBOARD_COOKIE_DOMAIN`. A host-only
    // deletion would not match them, and a valid session would survive logout.
    vi.stubEnv("DASHBOARD_COOKIE_DOMAIN", ".example.com")
    const { event, res } = eventWithBody({ url: "/api/operator/session/logout" })

    appendSessionDeletionCookies(event)

    const cookies = setCookieList(res)
    expect(cookies).toHaveLength(3)
    for (const cookie of cookies) {
      expect(cookie).toContain("Max-Age=0")
      expect(cookie).toContain("Domain=.example.com")
    }
  })

  it("stays host-only when no Domain is configured", () => {
    const { event, res } = eventWithBody({ url: "/api/operator/session/logout" })

    appendSessionDeletionCookies(event)

    const cookies = setCookieList(res)
    expect(cookies).toHaveLength(3)
    for (const cookie of cookies) {
      expect(cookie).not.toContain("Domain=")
    }
  })

  it("ignores a malformed Domain instead of writing it into a header", () => {
    // A configured value must never inject a second attribute or header.
    vi.stubEnv("DASHBOARD_COOKIE_DOMAIN", ".example.com; HttpOnly")
    const { event, res } = eventWithBody({ url: "/api/operator/session/logout" })

    appendSessionDeletionCookies(event)

    for (const cookie of setCookieList(res)) {
      expect(cookie).not.toContain("Domain=")
    }
  })
})

describe("cleartext API origin", () => {
  it("refuses to forward a PAT when no cookie is present", async () => {
    // Login has no cookie yet, so a cookie-only guard sent the PAT in
    // plaintext over http://. The credential, not the cookie, is the trigger.
    vi.stubEnv("IBEX_OPERATOR_API_ORIGIN", "http://operator-api.internal:8010")
    const body = JSON.stringify({ pat: "ibex_pat_123456789" })
    const { event } = eventWithBody({
      body,
      headers: { "content-type": "application/json", "content-length": String(Buffer.byteLength(body)) },
    })
    const fetchMock = stubFetch(() => upstream({ status: "ok" }))

    await expect(loginHandler(event)).rejects.toMatchObject({
      statusCode: 503,
      data: { error: { code: "API_ORIGIN_INSECURE" } },
    })
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
