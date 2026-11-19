import { createRequire } from "node:module"
import { expect, test, type Page } from "@playwright/test"

const require = createRequire(import.meta.url)

/**
 * A1 — a refusal has to carry the remedy it names.
 *
 * The session journeys prove the routes work: `/login` exchanges a token and
 * `/logout` revokes the family. They start by navigating to those routes
 * directly, which a person cannot do from a refusal. This spec starts where a
 * person does — a live surface with no session — and asserts the two ways in:
 * the refusal verdict offers a real link to the sign-in page, and the session
 * menu offers a real button to the sign-out route.
 *
 * The first case makes the refusal happen rather than waiting for a stack: the
 * dev server has no operator API, so its reads fail with a connection error.
 * Intercepting the browser-side reads with the API's 401 is the same refusal
 * the live suite meets, and it exercises the real page, verdict, link and
 * navigation. The 401 itself is covered against the stand-in upstream elsewhere.
 */

async function waitForHydration(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const root = document.querySelector("#__nuxt") as (HTMLElement & { __vue_app__?: unknown }) | null
    const provider = document.querySelector('[data-console-hydrated="true"]')
    return Boolean(root?.__vue_app__ && provider)
  })
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()))
      }),
  )
}

async function expectNoAxeViolations(page: Page, selector?: string): Promise<void> {
  await page.addScriptTag({ path: require.resolve("axe-core") })
  const accessibility = await page.evaluate(async (contextSelector) => {
    const axe = (window as Window & {
      axe?: {
        run: (
          context: Document | Element,
          options: object,
        ) => Promise<{
          violations: Array<{
            id: string
            impact: string | null
            help: string
            nodes: Array<{ target: string[] }>
          }>
        }>
      }
    }).axe
    if (!axe) throw new Error("axe-core did not load")
    const context = contextSelector ? document.querySelector(contextSelector) : document
    if (!context) throw new Error(`axe context not found: ${contextSelector}`)
    const result = await axe.run(context, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
    })
    return result.violations.map(({ id, impact, help, nodes }) => ({
      id,
      impact,
      help,
      targets: nodes.flatMap((node) => node.target),
    }))
  }, selector)
  expect(accessibility).toEqual([])
}

test("a session can be started from the verdict that asks for one", async ({ page }) => {
  await page.goto("/?demo=0")
  await waitForHydration(page)

  // Turn the reads the page already made into the API's session refusal. Only
  // the tenant-scoped reads are intercepted; the session routes are not.
  await page.route(/\/api\/operator\/(context|overview|platform\/health|traces)/, (route) =>
    route.fulfill({
      status: 401,
      contentType: "application/json",
      body: JSON.stringify({
        error: { code: "UNAUTHENTICATED", message: "Operator session required" },
      }),
    }),
  )
  await page.getByRole("button", { name: "Re-read" }).click()

  // The verdict keeps the sentence it already had, and now offers the action.
  await expect(
    page.getByRole("heading", { name: "Sign in to read this organization." }),
  ).toBeVisible()
  const signIn = page.getByRole("link", { name: "Sign in", exact: true })
  await expect(signIn).toBeVisible()
  await expect(signIn).toHaveAttribute("href", /^\/login(\?next=[^/]+)?$/)
  await expectNoAxeViolations(page)

  await signIn.click()
  await expect(page).toHaveURL(/\/login(\?next=[^/]+)?$/)
  await expect(page.getByRole("heading", { name: "Sign in to IBEX Console" })).toBeVisible()
})

/**
 * B3/B4 — a trace read that fails on its own, inside a page that is readable.
 *
 * The organization snapshot and platform health resolve for this session, so the
 * missing trace read is a panel-level gap, not a page-level refusal: the verdict
 * keeps its normal sentence and the runs panel carries the remedy. The two
 * refusal statuses are not the same remedy — 401 means there is no signed-in
 * session, 403 means the session is signed in without the trace grant.
 */
const LIVE_CONTEXT = {
  schema_version: "operator.context.v1",
  org_name: "Northwind",
  org_slug: "org_demo_42",
  org_status: "active",
  role: "admin",
}

const LIVE_OVERVIEW = {
  schema_version: "operator.overview.v1",
  org_name: "Northwind",
  org_slug: "org_demo_42",
  org_status: "active",
  counts: { active_users: 4, agents: 9, active_agents: 6 },
  completeness: "complete",
}

const LIVE_HEALTH = {
  dependency_health: { postgres: "ok", redis: "ok" },
  last_backup_at: "2026-11-18T02:00:00Z",
  last_restore_drill: { completed_at: "2026-11-01T03:00:00Z", duration_seconds: 1_440 },
  retention_horizon_days: 90,
  ingestion_lag_seconds: 3,
  dlq_depth: 0,
  degraded_mode: false,
  outbox_max_aggregate_seq: 41,
  deploy_image_digest: "sha256:1f2c3d",
}

/** Refuse the trace read only: the other three reads answer as a signed-in session. */
async function serveReadsExceptTraces(page: Page, traceStatus: 401 | 403): Promise<void> {
  const observed = () => new Date().toISOString()
  await page.route(/\/api\/operator\/context$/, (route) =>
    route.fulfill({ json: { ...LIVE_CONTEXT, observed_at: observed() } }),
  )
  await page.route(/\/api\/operator\/overview$/, (route) =>
    route.fulfill({ json: { ...LIVE_OVERVIEW, observed_at: observed() } }),
  )
  await page.route(/\/api\/operator\/platform\/health$/, (route) =>
    route.fulfill({ json: { ...LIVE_HEALTH, observed_at: observed() } }),
  )
  await page.route(/\/api\/operator\/traces(\?.*)?$/, (route) =>
    route.fulfill({
      status: traceStatus,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: traceStatus === 401 ? "UNAUTHENTICATED" : "PERMISSION_DENIED",
          message: traceStatus === 401 ? "Operator session required" : "Trace read not granted",
        },
      }),
    }),
  )
}

test("a trace-only 401 offers the sign-in the session needs", async ({ page }) => {
  await page.goto("/?demo=0&tab=runs")
  await waitForHydration(page)
  await serveReadsExceptTraces(page, 401)
  await page.getByRole("button", { name: "Re-read" }).click()

  // The page-level verdict is not a refusal: the snapshot and health were read,
  // and their values stay on screen.
  await expect(page.getByRole("heading", { name: "Sign in to read this organization." })).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "1 reported finding; none is critical." })).toBeVisible()

  const runs = page.getByRole("region", { name: "Recent runs" })
  await expect(runs.getByText("Run metadata needs a signed-in session", { exact: true })).toBeVisible()
  await expect(runs.getByText(/is not signed in/)).toBeVisible()
  // Not the retryable failure: a 401 is answered by a session, not a second read.
  await expect(runs.getByRole("button", { name: "Retry this read" })).toHaveCount(0)

  const signIn = page.getByRole("link", { name: "Sign in", exact: true })
  await expect(signIn).toHaveCount(1)
  await expect(signIn).toHaveAttribute("href", /^\/login\?next=/)
  const next = new URL(await signIn.getAttribute("href") ?? "", "https://console.example").searchParams.get("next")
  expect(next).toBe("/?demo=0&tab=runs")
  await expectNoAxeViolations(page)

  await signIn.click()
  await expect(page).toHaveURL(/\/login\?next=/)
  await expect(page.getByRole("heading", { name: "Sign in to IBEX Console" })).toBeVisible()
})

test("a trace-only 403 refuses without a sign-in that cannot help", async ({ page }) => {
  await page.goto("/?demo=0&tab=runs")
  await waitForHydration(page)
  await serveReadsExceptTraces(page, 403)
  await page.getByRole("button", { name: "Re-read" }).click()

  // Same page-level verdict: authorization is not authentication, and this
  // session can still read everything else on the screen.
  await expect(page.getByRole("heading", { name: "Sign in to read this organization." })).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "1 reported finding; none is critical." })).toBeVisible()

  const runs = page.getByRole("region", { name: "Recent runs" })
  await expect(runs.getByText("Run metadata needs the metadata read permission", { exact: true })).toBeVisible()
  await expect(runs.getByText(/Signing in again does not add this permission/)).toBeVisible()
  await expect(runs.getByRole("button", { name: "Retry this read" })).toHaveCount(0)
  await expect(page.getByRole("link", { name: "Sign in", exact: true })).toHaveCount(0)
  await expectNoAxeViolations(page)
})

test("a session can be ended from the session menu", async ({ page }) => {
  await page.goto("/")
  await waitForHydration(page)

  await page.getByRole("button", { name: "Session and organization menu" }).click()
  const signOut = page.getByRole("menuitem", { name: "Sign out" })
  await expect(signOut).toBeVisible()
  // A keyboard-operable control, not a menu-styled div.
  await expect(signOut).toHaveJSProperty("tagName", "BUTTON")
  // Scoped to the open menu: a modal dropdown hides the rest of the page with
  // `aria-hidden` (reka-ui), which axe reports as `aria-hidden-focus` whether or
  // not this item exists. The page-wide check runs where the page is reachable.
  await expectNoAxeViolations(page, '[role="menu"]')

  // The route is `/logout`, not a direct hop to the login page: the console
  // revocation call is what proves the menu item ends the session.
  const revocation = page.waitForRequest(
    (request) => new URL(request.url()).pathname === "/api/operator/session/logout",
  )
  await signOut.click()
  await revocation
  await expect(page).toHaveURL(/\/login(\?next=[^/]+)?$/)
  await expect(page.getByRole("heading", { name: "Sign in to IBEX Console" })).toBeVisible()
})
