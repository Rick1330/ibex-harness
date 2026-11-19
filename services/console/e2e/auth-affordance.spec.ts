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
