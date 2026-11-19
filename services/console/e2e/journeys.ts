import { expect, type APIRequestContext, type APIResponse, type BrowserContext, type Page } from "@playwright/test"

/**
 * Shared plumbing for the Console session journeys.
 *
 * The journeys run against `e2e/live-stack.mjs`, which serves a loopback HTTPS
 * operator API and the real Nuxt server path (see `playwright.live.config.ts`).
 * The stand-in implements the API's session contract — PAT exchange, single-use
 * refresh rotation, CSRF double-submit, revocation — and resolves every read
 * through the session's org, so a journey here is the Console's own contract
 * end to end. The upstream issuance rules themselves are covered by
 * `services/api/tests/unit/operator/test_operator_session*.py`.
 *
 * The two orgs below are the stand-in's tenants. They exist so a browser can
 * hold two sessions at once; they are not fixtures rendered by the app.
 */

export const apiOrigin = "https://127.0.0.1:3283"
export const consoleOrigin = "https://127.0.0.1:3282"

export type TenantOrg = {
  name: string
  slug: string
  pat: string
  agentId: string
  agentName: string
  agentSlug: string
}

export const ORG_A: TenantOrg = {
  name: "Live Workspace",
  slug: "live-workspace",
  pat: "pat-live-workspace-fixture",
  agentId: "33333333-3333-4333-8333-333333333333",
  agentName: "Support Agent",
  agentSlug: "support-agent",
}

export const ORG_B: TenantOrg = {
  name: "Second Workspace",
  slug: "second-workspace",
  pat: "pat-second-workspace-fixture",
  agentId: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  agentName: "Billing Agent",
  agentSlug: "billing-agent",
}

/** Access cookie the browser holds while a session is live. */
export const ACCESS_COOKIE = "ibex_session"
export const REFRESH_COOKIE = "ibex_refresh"
export const CSRF_COOKIE = "ibex_csrf"

export type StandInRequest = {
  method: string
  path: string
  cookieNames: string[]
  lastEventId: string | null
  /** Origin the caller sent, exactly as the API's origin rule read it. */
  origin: string | null
  referer: string | null
  /** Stand-in org key the access cookie resolved to, or null when it refused. */
  org: string | null
  /** Status the stand-in answered with. */
  status: number | null
}

export async function resetStandIn(api: APIRequestContext): Promise<void> {
  const response = await api.post(`${apiOrigin}/__test/reset`)
  expect(response.status()).toBe(204)
}

export async function standInRequests(api: APIRequestContext): Promise<StandInRequest[]> {
  const response = await api.get(`${apiOrigin}/__test/requests`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as StandInRequest[]
}

/** Vue mounted on the document. Pages without the console layout need only this. */
export async function waitForVue(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const root = document.querySelector("#__nuxt") as (HTMLElement & { __vue_app__?: unknown }) | null
    return Boolean(root?.__vue_app__)
  })
}

/** Vue mounted and the console layout hydrated — the marker live pages expose. */
export async function waitForHydration(page: Page): Promise<void> {
  await waitForVue(page)
  await page.locator('[data-console-hydrated="true"]').waitFor({ state: "attached" })
}

export async function cookieValue(
  context: BrowserContext,
  name: string,
): Promise<string | undefined> {
  const cookies = await context.cookies(consoleOrigin)
  return cookies.find((cookie) => cookie.name === name)?.value
}

export async function cookie(
  context: BrowserContext,
  name: string,
): Promise<{ value: string; httpOnly: boolean; secure: boolean } | undefined> {
  const cookies = await context.cookies(consoleOrigin)
  const match = cookies.find((candidate) => candidate.name === name)
  if (!match) return undefined
  return { value: match.value, httpOnly: match.httpOnly, secure: match.secure }
}

/** The three cookies one operator session consists of. */
export type SessionCookies = { access: string; refresh: string; csrf: string }

function requiredCookie(values: Record<string, string>, name: string): string {
  const value = values[name]
  if (!value) throw new Error(`the stand-in did not issue ${name}`)
  return value
}

/** The session a browser context currently holds, failing loudly if partial. */
export async function sessionCookies(context: BrowserContext): Promise<SessionCookies> {
  const cookies = await context.cookies(consoleOrigin)
  const values = Object.fromEntries(
    cookies.map((candidate) => [candidate.name, candidate.value]),
  )
  return {
    access: requiredCookie(values, ACCESS_COOKIE),
    refresh: requiredCookie(values, REFRESH_COOKIE),
    csrf: requiredCookie(values, CSRF_COOKIE),
  }
}

/** `Set-Cookie` name=value pairs from one stand-in response. */
function responseCookies(response: APIResponse): Record<string, string> {
  const values: Record<string, string> = {}
  for (const header of response.headersArray()) {
    if (header.name.toLowerCase() !== "set-cookie") continue
    const pair = header.value.split(";", 1)[0] ?? ""
    const separator = pair.indexOf("=")
    if (separator < 0) continue
    values[pair.slice(0, separator).trim()] = pair.slice(separator + 1).trim()
  }
  return values
}

/**
 * Sign in against the stand-in directly, skipping the console's BFF.
 *
 * The BFF relays the browser's cookies but always supplies its own `Origin` for
 * a server-side rotation, and a browser cannot be told to send a foreign one.
 * A rule the console cannot express through the browser is therefore pinned
 * here, at the API boundary the console's relay is supposed to satisfy.
 */
export async function loginDirect(
  api: APIRequestContext,
  pat: string,
): Promise<SessionCookies> {
  const response = await api.post(`${apiOrigin}/v1/operator/session/login`, {
    headers: { origin: consoleOrigin },
    data: { pat },
    failOnStatusCode: false,
  })
  expect(response.status(), "direct login").toBe(200)
  const cookies = responseCookies(response)
  return {
    access: requiredCookie(cookies, ACCESS_COOKIE),
    refresh: requiredCookie(cookies, REFRESH_COOKIE),
    csrf: requiredCookie(cookies, CSRF_COOKIE),
  }
}

/**
 * POST one session action to the stand-in with this session's cookies and CSRF
 * proof. `origin` and `referer` are omitted entirely when not supplied, which is
 * the case the API's origin rule must refuse.
 */
export async function postSessionDirect(
  api: APIRequestContext,
  action: "refresh" | "logout",
  session: SessionCookies,
  headers: { origin?: string; referer?: string } = {},
): Promise<APIResponse> {
  return api.post(`${apiOrigin}/v1/operator/session/${action}`, {
    headers: {
      cookie: `${ACCESS_COOKIE}=${session.access}; ${REFRESH_COOKIE}=${session.refresh}; ${CSRF_COOKIE}=${session.csrf}`,
      "x-csrf-token": session.csrf,
      ...headers,
    },
    failOnStatusCode: false,
  })
}

/** The stable error code the stand-in answered with, or "" for a success. */
export async function sessionErrorCode(response: APIResponse): Promise<string> {
  const body = (await response.json()) as { error?: { code?: string } }
  return body.error?.code ?? ""
}

/**
 * Sign in through the console's own login page: no cookie is pre-seeded, and the
 * PAT travels only in the form body to the same-origin BFF route.
 */
export async function signIn(page: Page, pat: string): Promise<void> {
  await page.goto("/login")
  await waitForVue(page)
  await expect(page.getByRole("heading", { name: "Sign in to IBEX Console" })).toBeVisible()
  await page.getByLabel("Personal access token").fill(pat)
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
  await expect(page).toHaveURL(`${consoleOrigin}/`)
  await waitForHydration(page)
}
