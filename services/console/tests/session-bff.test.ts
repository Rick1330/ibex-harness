import { IncomingMessage, ServerResponse } from "node:http"
import { Socket } from "node:net"

import { createEvent, type H3Event } from "h3"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import bootstrapHandler from "../server/api/operator/session/bootstrap.get"
import loginHandler from "../server/api/operator/session/login.post"
import logoutHandler from "../server/api/operator/session/logout.post"
import {
  OperatorLoginRedirect,
  OperatorUpstreamError,
  appendSessionDeletionCookies,
  callOperatorSession,
  fetchOperatorJson,
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

beforeEach(() => {
  vi.stubEnv("IBEX_OPERATOR_API_ORIGIN", API_ORIGIN)
  vi.stubGlobal("useRuntimeConfig", () => ({ operatorApiOrigin: "" }))
})

afterEach(() => {
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

  it("redirects a data fetch to /login without refreshing when there is no refresh cookie", async () => {
    // Fail closed: no data and no invented payload. With nothing to rotate, the
    // API must not be asked to refresh, and the operator is sent to sign in.
    const { event, res } = fakeEvent({
      url: "/api/operator/overview",
      headers: { accept: "application/json", cookie: "ibex_session=expired" },
    })
    const fetchMock = stubFetch(() =>
      upstream({ error: { code: "INVALID_SESSION", message: "Session required" } }, { status: 401 }),
    )

    await expect(fetchOperatorJson(event, "overview", (value) => value)).rejects.toBeInstanceOf(
      OperatorLoginRedirect,
    )

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(res.statusCode).toBe(302)
    expect(headerValue(res.getHeader("location"))).toBe(
      `/login?next=${encodeURIComponent("/api/operator/overview")}`,
    )
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

  it("redirects to /login when the refresh is refused", async () => {
    const { event, res } = fakeEvent({
      url: "/api/operator/overview?tab=1",
      headers: { accept: "application/json", cookie: "ibex_session=expired; ibex_refresh=stale" },
    })
    const fetchMock = stubFetch((target) =>
      target.pathname === "/v1/operator/session/refresh"
        ? upstream({ error: { code: "INVALID_TOKEN", message: "invalid refresh token" } }, { status: 401 })
        : upstream({ error: { code: "INVALID_SESSION", message: "expired" } }, { status: 401 }),
    )

    await expect(fetchOperatorJson(event, "overview", (value) => value)).rejects.toBeInstanceOf(
      OperatorLoginRedirect,
    )

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(res.statusCode).toBe(302)
    expect(headerValue(res.getHeader("location"))).toBe(
      `/login?next=${encodeURIComponent("/api/operator/overview?tab=1")}`,
    )
  })

  it("stops after one retry when the refreshed session is still rejected", async () => {
    // A second 401 must not trigger a second refresh: the retry flag is the
    // recursion guard, and the read still fails closed with a login redirect.
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

    await expect(fetchOperatorJson(event, "overview", (value) => value)).rejects.toBeInstanceOf(
      OperatorLoginRedirect,
    )

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(res.statusCode).toBe(302)
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
