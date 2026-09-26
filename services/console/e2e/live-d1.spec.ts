import { createRequire } from "node:module"

import { expect, type Page, test } from "@playwright/test"

const require = createRequire(import.meta.url)
const apiOrigin = "https://127.0.0.1:3283"
const consoleOrigin = "https://127.0.0.1:3282"

type FixtureRequest = {
  method: string
  path: string
  cookieNames: string[]
  lastEventId: string | null
}

async function resetFixtureApi(page: Page): Promise<void> {
  await page.request.post(`${apiOrigin}/__test/reset`)
}

async function seedOperatorCookies(page: Page): Promise<void> {
  await page.context().addCookies([
    {
      name: "ibex_session",
      value: "fixture-access-secret",
      url: consoleOrigin,
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    },
    {
      name: "ibex_refresh",
      value: "must-not-be-forwarded",
      url: consoleOrigin,
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    },
    {
      name: "ibex_csrf",
      value: "must-not-be-forwarded",
      url: consoleOrigin,
      secure: true,
      sameSite: "Lax",
    },
  ])
}

async function expectLiveDashboard(page: Page): Promise<void> {
  await page.goto("/dashboard")
  await expect(page.getByRole("heading", { name: "Live Workspace" })).toBeVisible()
  await expect(page.getByText("admin · live-workspace")).toBeVisible()
  await expect(page.getByText("7", { exact: true })).toBeVisible()
  await expect(page.getByText("SSE connected")).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("degraded · platform health")).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expect(page.getByText("No mock data is substituted").first()).toBeVisible()
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  await page.addScriptTag({ path: require.resolve("axe-core") })
  const accessibility = await page.evaluate(async () => {
    const axe = (window as Window & {
      axe?: {
        run: (
          context: Document,
          options: object,
        ) => Promise<{ violations: Array<{ id: string; impact: string | null; help: string }> }>
      }
    }).axe
    if (!axe) throw new Error("axe-core did not load")
    const result = await axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
    })
    return result.violations.map(({ id, impact, help }) => ({ id, impact, help }))
  })
  expect(accessibility).toEqual([])
}

async function fetchFixtureRequests(page: Page): Promise<FixtureRequest[]> {
  const response = await page.request.get(`${apiOrigin}/__test/requests`)
  expect(response.ok()).toBe(true)
  return (await response.json()) as FixtureRequest[]
}

async function expectOperatorApiPathsHit(page: Page): Promise<FixtureRequest[]> {
  const requests = await fetchFixtureRequests(page)
  for (const path of [
    "/v1/operator/context",
    "/v1/operator/overview",
    "/v1/operator/platform/health",
    "/v1/operator/events/stream",
  ]) {
    expect(requests.some((request) => request.path === path), path).toBe(true)
  }
  return requests
}

async function expectSseResumeWithLastEventId(page: Page): Promise<void> {
  await expect
    .poll(
      async () => {
        const entries = await fetchFixtureRequests(page)
        return entries.some(
          (request) =>
            request.path === "/v1/operator/events/stream" && request.lastEventId === "42",
        )
      },
      { timeout: 15_000 },
    )
    .toBe(true)
}

async function expectEventPayloadNotRetained(page: Page): Promise<void> {
  expect(await page.locator("body").innerText()).not.toContain("EVENT_PAYLOAD_SHOULD_NOT_RENDER")
  const storedValues = await page.evaluate(() => {
    const values = (storage: Storage) =>
      Array.from({ length: storage.length }, (_, index) => {
        const key = storage.key(index)
        return key ? `${key}=${storage.getItem(key)}` : ""
      }).join("\n")
    return `${values(localStorage)}\n${values(sessionStorage)}`
  })
  expect(storedValues).not.toContain("EVENT_PAYLOAD_SHOULD_NOT_RENDER")
}

async function expectForwardedCookiesAreAccessOnly(page: Page): Promise<void> {
  const allRequests = await fetchFixtureRequests(page)
  for (const request of allRequests) {
    expect(request.cookieNames).toEqual(["ibex_session"])
    expect(request.path).not.toMatch(/\/v1\/(agents|users)(\/|$)/)
  }
  expect(
    allRequests.some(
      (request) => request.path === "/v1/operator/events/stream" && request.lastEventId === "42",
    ),
  ).toBe(true)
}

test("live D1 renders tenant-scoped API data and forwards only the access cookie", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)
  await expectLiveDashboard(page)
  await expectNoAxeViolations(page)

  expect(await page.evaluate(() => document.cookie)).not.toContain("ibex_session=")

  await expectOperatorApiPathsHit(page)
  await expectSseResumeWithLastEventId(page)
  await expectEventPayloadNotRetained(page)
  await expectForwardedCookiesAreAccessOnly(page)
})
