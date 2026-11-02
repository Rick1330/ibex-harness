import { createRequire } from "node:module"

import { expect, type Page, test } from "@playwright/test"

const require = createRequire(import.meta.url)
const apiOrigin = "https://127.0.0.1:3283"
const consoleOrigin = "https://127.0.0.1:3282"
const runId = "11111111-1111-4111-8111-111111111111"

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

async function waitForHydration(page: Page): Promise<void> {
  await page.locator('[data-console-hydrated="true"]').waitFor({ state: "attached" })
}

async function expectLiveOverview(page: Page): Promise<void> {
  await page.goto("/")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible()
  await expect(page.getByText(/Live Workspace · live-workspace/)).toBeVisible()
  await expect(page.getByText("7", { exact: true })).toBeVisible()
  await expect(page.getByText("Redis reported degraded")).toBeVisible()
  await page.getByRole("tab", { name: /Sources and session/ }).click()
  await expect(page.locator('[data-stream-state="connected"]')).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
}

async function expectNoAxeViolations(page: Page): Promise<void> {
  await page.addScriptTag({ path: require.resolve("axe-core") })
  const accessibility = await page.evaluate(async () => {
    const axe = (window as Window & {
      axe?: {
        run: (
          context: Document,
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
    const result = await axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
    })
    return result.violations.map(({ id, impact, help, nodes }) => ({
      id,
      impact,
      help,
      targets: nodes.flatMap((node) => node.target),
    }))
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
  await expectLiveOverview(page)
  await expectNoAxeViolations(page)

  expect(await page.evaluate(() => document.cookie)).not.toContain("ibex_session=")

  await expectOperatorApiPathsHit(page)
  await expectSseResumeWithLastEventId(page)
  await expectEventPayloadNotRetained(page)
  await expectForwardedCookiesAreAccessOnly(page)
})

test("live D2 Explore and run inspector stay fixture-free with axe coverage", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)
  await page.goto("/explore?limit=50&status=ok")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Explore", exact: true })).toBeVisible()
  await expect(page.getByText("trace-live-1")).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expectNoAxeViolations(page)

  await page.goto(`/explore/r/${runId}?return=%2Fexplore`)
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: /^Run / })).toBeVisible()
  await expect(page.getByText("trace-live-1").first()).toBeVisible()
  await page.getByRole("tab", { name: "Evidence" }).click()
  await expect(page.getByLabel("Evidence record").getByText("Published", { exact: true })).toBeVisible()
  await expect(page.getByText(/sections are explicitly unrecorded/)).toBeVisible()
  await expectNoAxeViolations(page)

  await page.goto("/explore/r/22222222-2222-4222-8222-222222222222")
  await expect(page.getByRole("heading", { name: /Run evidence unavailable/ })).toBeVisible()
})

test("live Platform renders readiness, dependency state, and snapshot evidence", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)
  await page.goto("/platform")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Platform", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "1 of 2 dependencies are not reporting ok." })).toBeVisible()
  await expect(page.getByText("Database", { exact: true })).toBeVisible()
  const redisRow = page.getByRole("row").filter({ hasText: "Redis" })
  await expect(redisRow).toBeVisible()
  await expect(redisRow.getByText("Degraded", { exact: true })).toBeVisible()
  await expect(page.getByText("Check latency history")).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)

  await page.getByRole("tab", { name: "Snapshot payload" }).click()
  await expect(page.locator("pre").filter({ hasText: '"dependency_health"' })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("live Agents renders the operator inventory and detail with axe coverage", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)

  await page.goto("/agents")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Agents", exact: true })).toBeVisible()
  await expect(page.getByText("Showing 1 agent from the operator API.")).toBeVisible()
  await expect(page.getByRole("link", { name: "Support Agent" })).toBeVisible()
  await expect(page.getByText("support-agent", { exact: true })).toBeVisible()
  await expect(page.getByText("openai · gpt-4.1")).toBeVisible()
  await expect(page.getByText("42", { exact: true })).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expectNoAxeViolations(page)

  const listRequests = await fetchFixtureRequests(page)
  expect(listRequests.some((request) => request.path === "/v1/operator/agents")).toBe(true)
  for (const request of listRequests.filter((entry) => entry.path === "/v1/operator/agents")) {
    expect(request.cookieNames).toEqual(["ibex_session"])
  }

  await page.getByRole("link", { name: "Support Agent" }).click()
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Support Agent", exact: true })).toBeVisible()
  await expect(
    page.locator("dd").filter({ hasText: "33333333-3333-4333-8333-333333333333" }),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "Copy agent ID" })).toBeVisible()
  await expect(page.getByText("901,234")).toBeVisible()
  await expectNoAxeViolations(page)
})

test("live Memories renders the metadata index and detail with axe coverage", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)

  await page.goto("/memories")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Memories", exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: /44444444/ })).toBeVisible()
  await expect(page.getByText("factual", { exact: true })).toBeVisible()
  await expect(page.getByText("12", { exact: true })).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expectNoAxeViolations(page)

  const listRequests = await fetchFixtureRequests(page)
  expect(listRequests.some((request) => request.path === "/v1/operator/memories")).toBe(true)
  for (const request of listRequests.filter((entry) => entry.path === "/v1/operator/memories")) {
    expect(request.cookieNames).toEqual(["ibex_session"])
  }

  await page.getByRole("link", { name: /44444444/ }).click()
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: /Memory 44444444/ })).toBeVisible()
  await expect(
    page.locator("dd").filter({ hasText: "33333333-3333-4333-8333-333333333333" }),
  ).toBeVisible()
  await expect(page.getByText("Content tokens")).toBeVisible()
  await expectNoAxeViolations(page)
})

test("live Sessions renders the turn ledger and trace link with axe coverage", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)

  await page.goto("/sessions")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Sessions", exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: /88888888/ })).toBeVisible()
  await expect(page.locator("tr[data-session-row]").getByText("Completed", { exact: true })).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expectNoAxeViolations(page)

  const listRequests = await fetchFixtureRequests(page)
  expect(listRequests.some((request) => request.path === "/v1/operator/sessions")).toBe(true)
  for (const request of listRequests.filter((entry) => entry.path === "/v1/operator/sessions")) {
    expect(request.cookieNames).toEqual(["ibex_session"])
  }

  await page.getByRole("link", { name: /88888888/ }).click()
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: /Session 88888888/ })).toBeVisible()
  await expect(page.getByRole("link", { name: /trace-live-1/ })).toBeVisible()
  await expect(page.getByText("No evidence")).toHaveCount(0)
  await expectNoAxeViolations(page)
})
