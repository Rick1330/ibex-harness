import { expect, test } from "@playwright/test"
import {
  ACCESS_COOKIE,
  CSRF_COOKIE,
  ORG_A,
  REFRESH_COOKIE,
  cookie,
  cookieValue,
  consoleOrigin,
  resetStandIn,
  signIn,
  standInRequests,
  waitForHydration,
  waitForVue,
} from "./journeys"

/**
 * P0-04 — the clean-browser session journey.
 *
 * `live-d1.spec.ts` starts from a session the test mints itself, so it proves a
 * page renders *given* a session and nothing about how a person gets one. This
 * journey starts from an empty cookie jar and drives the surfaces that ship:
 * `/login`, `POST /api/operator/session/login`, the server-side refresh rotation
 * the console actually uses, `/logout`, and `POST /api/operator/session/logout`.
 *
 * The upstream operator API is the loopback stand-in in `e2e/live-stack.mjs`,
 * which implements the API's session rules rather than bypassing them. It is the
 * same seam `live-d1.spec.ts` already runs against; what changes is that no
 * cookie is supplied to the browser and every step that issues, rotates or
 * revokes one is exercised through the real Nuxt server path.
 */

test("a clean browser signs in, reads live data, rotates an expired access cookie, and signs out", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  await resetStandIn(request)

  // A browser that has never visited the console holds no session cookies, and
  // a live surface with no session reports that rather than inventing a tenant.
  expect(await page.context().cookies()).toEqual([])
  await page.goto("/?demo=0")
  await waitForHydration(page)
  await expect(
    page.getByRole("heading", { name: "Sign in to read this organization." }),
  ).toBeVisible()

  await signIn(page, ORG_A.pat)

  // The login route relayed the API's cookies to the console origin, and the
  // PAT was not left anywhere a later script or shared URL could read it.
  const access = await cookie(page.context(), ACCESS_COOKIE)
  expect(access, "login issued an access cookie").toBeDefined()
  expect(access?.httpOnly, "the access cookie is HttpOnly").toBe(true)
  expect(access?.secure, "the access cookie is Secure").toBe(true)
  expect((await cookie(page.context(), REFRESH_COOKIE))?.httpOnly).toBe(true)
  expect((await cookie(page.context(), CSRF_COOKIE))?.httpOnly).toBe(false)

  const readableCookies = await page.evaluate(() => document.cookie)
  expect(readableCookies).not.toContain(`${ACCESS_COOKIE}=`)
  expect(readableCookies).not.toContain(`${REFRESH_COOKIE}=`)
  expect(readableCookies).toContain(`${CSRF_COOKIE}=`)

  expect(page.url()).not.toContain(ORG_A.pat)
  const storage = await page.evaluate(() => {
    const dump = (store: Storage) =>
      Array.from({ length: store.length }, (_, index) => {
        const key = store.key(index)
        return key ? `${key}=${store.getItem(key)}` : ""
      }).join("\n")
    return `${dump(localStorage)}\n${dump(sessionStorage)}`
  })
  expect(storage).not.toContain(ORG_A.pat)

  // The page shows values only the operator API reported for this org.
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible()
  await expect(page.getByText(/Live Workspace · live-workspace/)).toBeVisible()
  await expect(page.getByText("7", { exact: true })).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)

  // Those values came from the API, on the cookie this login issued: the
  // stand-in only answers a token it minted, and it only answered for org A.
  await expect
    .poll(async () => {
      const entries = await standInRequests(request)
      return entries
        .filter((entry) => entry.status === 200 && entry.org === "a")
        .map((entry) => entry.path)
    })
    .toEqual(
      expect.arrayContaining(["/v1/operator/context", "/v1/operator/overview"]),
    )

  // Every read the API answered for this org carried the access cookie and
  // nothing else: refresh and CSRF never cross the read path.
  const reads = (await standInRequests(request)).filter(
    (entry) =>
      entry.status === 200 &&
      entry.path.startsWith("/v1/operator/") &&
      !entry.path.startsWith("/v1/operator/session/") &&
      !entry.path.startsWith("/v1/operator/events/"),
  )
  expect(reads.length).toBeGreaterThan(0)
  for (const entry of reads) {
    expect(entry.cookieNames, entry.path).toEqual([ACCESS_COOKIE])
  }

  // Refresh step. The console does not call the refresh route from the browser:
  // an expired access cookie is rotated server-side on the next read, using the
  // refresh cookie. Dropping only the access cookie is exactly that state.
  const beforeRotation = access?.value
  expect(beforeRotation, "a token to rotate away from").toBeTruthy()
  await page.context().clearCookies({ name: ACCESS_COOKIE })
  expect(await cookieValue(page.context(), ACCESS_COOKIE)).toBeUndefined()

  await page.reload()
  await waitForHydration(page)
  await expect(page.getByText(/Live Workspace · live-workspace/)).toBeVisible()
  await expect(page.getByText("7", { exact: true })).toBeVisible()

  const rotated = await cookieValue(page.context(), ACCESS_COOKIE)
  expect(rotated, "the rotation reissued an access cookie").toBeTruthy()
  expect(rotated).not.toBe(beforeRotation)

  const rotations = (await standInRequests(request)).filter(
    (entry) => entry.path === "/v1/operator/session/refresh",
  )
  // One rotation, however many reads raced for it: the BFF shares the result
  // rather than replaying an already-consumed refresh token.
  expect(rotations).toHaveLength(1)
  expect(rotations[0]?.status).toBe(200)

  // Sign out through the console's own route.
  await page.goto("/logout")
  await expect(page).toHaveURL(`${consoleOrigin}/login`)
  await expect(page.getByRole("heading", { name: "Sign in to IBEX Console" })).toBeVisible()
  expect(await page.context().cookies(consoleOrigin)).toEqual([])

  // The session is revoked upstream too, not merely deleted in this browser.
  const replay = await request.get("/api/operator/overview", {
    headers: { cookie: `${ACCESS_COOKIE}=${rotated}` },
  })
  expect(replay.status()).toBe(401)

  // And the live page no longer renders this org's data. `demo=0` pins the
  // fail-closed path: development fixtures are compile-time `import.meta.dev`
  // and never ship, so production has only this branch.
  await page.goto("/?demo=0")
  await waitForHydration(page)
  await expect(
    page.getByRole("heading", { name: "Sign in to read this organization." }),
  ).toBeVisible()
  await expect(page.getByText(/Live Workspace · live-workspace/)).toHaveCount(0)

  const entries = await standInRequests(request)
  const signedOutAt = entries.findIndex(
    (entry) => entry.path === "/v1/operator/session/logout",
  )
  expect(signedOutAt).toBeGreaterThan(-1)
  expect(
    entries.slice(signedOutAt + 1).filter((entry) => entry.org !== null),
  ).toEqual([])
})

test("a rejected personal access token leaves the browser without a session", async ({
  page,
  request,
}) => {
  await resetStandIn(request)

  await page.goto("/login")
  await waitForVue(page)
  await page
    .getByLabel("Personal access token")
    .fill("pat-not-issued-by-any-organization")
  await page.getByRole("button", { name: "Sign in", exact: true }).click()

  // The BFF forwards the API's refusal as the stable sign-in message, and the
  // form stays on the login page with no cookie issued.
  await expect(page.getByRole("alert")).toHaveText(
    "That personal access token was not accepted.",
  )
  await expect(page.getByRole("heading", { name: "Sign in to IBEX Console" })).toBeVisible()
  expect(await page.context().cookies(consoleOrigin)).toEqual([])

  const logins = (await standInRequests(request)).filter(
    (entry) => entry.path === "/v1/operator/session/login",
  )
  expect(logins).toHaveLength(1)
  expect(logins[0]?.status).toBe(401)

  // A refused login does not become a session by navigating at the console.
  await page.goto("/?demo=0")
  await waitForHydration(page)
  await expect(
    page.getByRole("heading", { name: "Sign in to read this organization." }),
  ).toBeVisible()
})
