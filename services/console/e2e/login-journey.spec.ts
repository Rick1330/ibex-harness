import { expect, test } from "@playwright/test"
import {
  ACCESS_COOKIE,
  CSRF_COOKIE,
  ORG_A,
  REFRESH_COOKIE,
  apiOrigin,
  cookie,
  cookieValue,
  consoleOrigin,
  loginDirect,
  postSessionDirect,
  resetStandIn,
  sessionCookies,
  sessionErrorCode,
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
  // A server-side rotation is driven by a GET, which carries no Origin of its
  // own, so the BFF must supply this console's origin. The API rejects the call
  // without one, and the session would be sent to login.
  expect(
    rotations[0]?.origin,
    "the BFF supplied this console's origin to the rotation",
  ).toBe(consoleOrigin)

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

test("a replayed refresh token revokes the session it rotated into", async ({
  page,
  request,
}) => {
  test.setTimeout(120_000)
  await resetStandIn(request)
  await signIn(page, ORG_A.pat)

  // The pair the login issued. Its refresh token is the one an attacker who
  // captured it would later replay.
  const first = await sessionCookies(page.context())

  // Rotate exactly as the console does: drop the access cookie and reload, so
  // the BFF refreshes server-side and relays the new pair.
  await page.context().clearCookies({ name: ACCESS_COOKIE })
  await page.reload()
  await waitForHydration(page)
  const rotated = await sessionCookies(page.context())
  expect(rotated.access, "the rotation reissued an access cookie").not.toBe(
    first.access,
  )
  expect(rotated.refresh, "the rotation reissued a refresh cookie").not.toBe(
    first.refresh,
  )

  // Replay the consumed token, with the origin and CSRF proof a same-origin
  // script would have. Refusal alone is not the property.
  const replay = await postSessionDirect(request, "refresh", first, {
    origin: consoleOrigin,
  })
  expect(replay.status(), "a replayed refresh token is refused").toBe(401)
  expect(await sessionErrorCode(replay)).toBe("INVALID_TOKEN")

  // The property is family revocation. `RefreshPair` rotates with the refresh
  // token's own `FamilyID`, so the pair the rotation just issued is a descendant
  // of the replayed family and must stop working with it.
  const descendant = await request.get("/api/operator/overview", {
    headers: { cookie: `${ACCESS_COOKIE}=${rotated.access}` },
  })
  expect(
    descendant.status(),
    "the access token issued by the rotation was revoked too",
  ).toBe(401)
})

/**
 * The origin rule, driven against the stand-in directly.
 *
 * A browser cannot be made to send a foreign `Origin` to the console, and the
 * BFF sets its own on a server-side rotation, so this half of the contract
 * cannot be expressed through the browser. It is pinned at the API boundary the
 * BFF's relay has to satisfy; the journey above proves the relay satisfies it.
 */
test("rotation and logout apply the API's origin rule, not only the CSRF proof", async ({
  request,
}) => {
  await resetStandIn(request)

  // A foreign origin is refused before the handler runs, so the refresh token
  // is still unconsumed afterwards. That ordering is the middleware's.
  const foreignSession = await loginDirect(request, ORG_A.pat)
  const foreign = await postSessionDirect(request, "refresh", foreignSession, {
    origin: "https://attacker.example",
  })
  expect(foreign.status(), "a foreign Origin is rejected").toBe(403)
  expect(await sessionErrorCode(foreign)).toBe("ORIGIN_REJECTED")

  // No Origin is not permission: without a Referer there is nothing to check.
  const bareSession = await loginDirect(request, ORG_A.pat)
  const bare = await postSessionDirect(request, "refresh", bareSession)
  expect(bare.status(), "a missing Origin and Referer is rejected").toBe(403)
  expect(await sessionErrorCode(bare)).toBe("ORIGIN_REJECTED")

  // A Referer is only a fallback when it is an allowed origin itself.
  const foreignRefererSession = await loginDirect(request, ORG_A.pat)
  const foreignReferer = await postSessionDirect(request, "refresh", foreignRefererSession, {
    referer: "https://attacker.example/collect",
  })
  expect(foreignReferer.status(), "a foreign Referer is rejected").toBe(403)
  expect(await sessionErrorCode(foreignReferer)).toBe("ORIGIN_REJECTED")

  const originSession = await loginDirect(request, ORG_A.pat)
  const viaOrigin = await postSessionDirect(request, "refresh", originSession, {
    origin: consoleOrigin,
  })
  expect(viaOrigin.status(), "an allowed Origin rotates").toBe(200)

  const refererSession = await loginDirect(request, ORG_A.pat)
  const viaReferer = await postSessionDirect(request, "refresh", refererSession, {
    referer: `${consoleOrigin}/agents/${ORG_A.agentId}`,
  })
  expect(viaReferer.status(), "an allowed Referer rotates when Origin is absent").toBe(200)

  // Logout applies the same rule, and a refused logout revokes nothing.
  const session = await loginDirect(request, ORG_A.pat)
  const refusedLogout = await postSessionDirect(request, "logout", session, {
    origin: "https://attacker.example",
  })
  expect(refusedLogout.status(), "a foreign Origin cannot log the session out").toBe(403)
  expect(await sessionErrorCode(refusedLogout)).toBe("ORIGIN_REJECTED")

  const stillLive = await request.get(`${apiOrigin}/v1/operator/overview`, {
    headers: { cookie: `${ACCESS_COOKIE}=${session.access}` },
  })
  expect(stillLive.status(), "a refused logout left the session live").toBe(200)

  const bareLogout = await postSessionDirect(request, "logout", session)
  expect(bareLogout.status(), "a missing Origin and Referer cannot log out").toBe(403)
  expect(await sessionErrorCode(bareLogout)).toBe("ORIGIN_REJECTED")

  const logout = await postSessionDirect(request, "logout", session, { origin: consoleOrigin })
  expect(logout.status(), "an allowed Origin logs out").toBe(200)

  const revoked = await request.get(`${apiOrigin}/v1/operator/overview`, {
    headers: { cookie: `${ACCESS_COOKIE}=${session.access}` },
  })
  expect(revoked.status(), "logout revoked the session upstream").toBe(401)
})
