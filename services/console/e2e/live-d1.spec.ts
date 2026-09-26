import { createRequire } from "node:module"

import { expect, test } from "@playwright/test"

const require = createRequire(import.meta.url)
const apiOrigin = "https://127.0.0.1:3283"

test("live D1 renders tenant-scoped API data and forwards only the access cookie", async ({ page }) => {
  await page.request.post(`${apiOrigin}/__test/reset`)
  await page.context().addCookies([
    {
      name: "ibex_session",
      value: "fixture-access-secret",
      url: "https://127.0.0.1:3282",
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    },
    {
      name: "ibex_refresh",
      value: "must-not-be-forwarded",
      url: "https://127.0.0.1:3282",
      httpOnly: true,
      secure: true,
      sameSite: "Lax",
    },
    {
      name: "ibex_csrf",
      value: "must-not-be-forwarded",
      url: "https://127.0.0.1:3282",
      secure: true,
      sameSite: "Lax",
    },
  ])

  await page.goto("/dashboard")
  await expect(page.getByRole("heading", { name: "Live Workspace" })).toBeVisible()
  await expect(page.getByText("admin · live-workspace")).toBeVisible()
  await expect(page.getByText("7", { exact: true })).toBeVisible()
  await expect(page.getByText("SSE connected")).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("degraded · platform health")).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expect(page.getByText("No mock data is substituted").first()).toBeVisible()

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

  expect(await page.evaluate(() => document.cookie)).not.toContain("ibex_session=")

  const requestsResponse = await page.request.get(`${apiOrigin}/__test/requests`)
  expect(requestsResponse.ok()).toBe(true)
  const requests = (await requestsResponse.json()) as Array<{
    method: string
    path: string
    cookieNames: string[]
    lastEventId: string | null
  }>
  for (const path of [
    "/v1/operator/context",
    "/v1/operator/overview",
    "/v1/operator/platform/health",
    "/v1/operator/events/stream",
  ]) {
    expect(requests.some((request) => request.path === path), path).toBe(true)
  }
  await expect
    .poll(
      async () => {
        const response = await page.request.get(`${apiOrigin}/__test/requests`)
        const entries = (await response.json()) as typeof requests
        return entries.some(
          (request) =>
            request.path === "/v1/operator/events/stream" && request.lastEventId === "42",
        )
      },
      { timeout: 15_000 },
    )
    .toBe(true)
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
  const allRequestsResponse = await page.request.get(`${apiOrigin}/__test/requests`)
  const allRequests = (await allRequestsResponse.json()) as typeof requests
  for (const request of allRequests) {
    expect(request.cookieNames).toEqual(["ibex_session"])
    expect(request.path).not.toMatch(/\/v1\/(agents|users)(\/|$)/)
  }
  expect(
    allRequests.some(
      (request) => request.path === "/v1/operator/events/stream" && request.lastEventId === "42",
    ),
  ).toBe(true)
})
