import { createRequire } from "node:module"

import { expect, type Page, test } from "@playwright/test"
import { expectHeaderLimitationInAbout } from "./header-disclosure"

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

/** Fail the next `count` reads of an operator path with a 503. */
async function failNextRead(page: Page, path: string, count = 1): Promise<void> {
  const response = await page.request.post(`${apiOrigin}/__test/fail`, { data: { path, count } })
  expect(response.ok()).toBe(true)
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

function escapeForRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
}

/**
 * The Health value shows the snapshot's age, and the header's Observed row
 * cannot carry the read time itself: that row is the newest of four reads. So
 * the absolute stamp has to reach a hover and a screen reader from the value,
 * without restoring the narration sentence the page deliberately dropped.
 */
async function expectHealthValueCarriesItsReadStamp(page: Page): Promise<void> {
  const health = page.locator("p > span[title]").filter({ hasText: /Health / })
  await expect(health).toHaveCount(1)

  // Hover: the tooltip is the platform snapshot's own read time, to the minute.
  const stamp = await health.getAttribute("title")
  if (!stamp) throw new Error("the Health value carries no absolute read time")
  expect(stamp).toMatch(/^\d{2} \S+ \d{4}, \d{2}:\d{2} UTC$/)

  // Screen reader: the stamp is in the accessibility tree for this value...
  await expect(health).toHaveAccessibleName(new RegExp(escapeForRegExp(stamp)))
  // ...and the text a reader traverses keeps the age beside it, not instead of it.
  const age = await health.locator("span").first().innerText()
  await expect(health).toContainText(
    new RegExp(`${escapeForRegExp(age)} \\(read ${escapeForRegExp(stamp)}\\)`),
  )

  // The stamp is carried by the value, not by a restored narration paragraph.
  await expect(page.getByText(/Findings below restate only what that read reported/)).toHaveCount(0)
}

async function expectLiveOverview(page: Page): Promise<void> {
  await page.goto("/")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible()
  await expect(page.getByText(/Live Workspace · live-workspace/)).toBeVisible()
  await expect(page.getByText("7", { exact: true })).toBeVisible()
  await expect(page.getByText("Redis reported degraded")).toBeVisible()
  await expectHealthValueCarriesItsReadStamp(page)
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
  await expect(page.locator("[data-agent-row]")).toHaveCount(1)
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
  await expectHeaderLimitationInAbout(
    page,
    "Support Agent",
    "Health, budget, environment, owner, and drift are not part of this contract and are not shown.",
  )
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
  await expectHeaderLimitationInAbout(
    page,
    /^Memory 44444444/,
    "Content, embeddings, and free-form metadata are not part of this contract and are not shown.",
  )
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
  // `total_latency_ms` is the sum of the turn rows below the tiles, not a
  // wall-clock duration, so the label states the aggregation and no helper
  // repeats it.
  await expect(page.getByText("Total turn latency", { exact: true })).toBeVisible()
  await expect(page.getByText("Turn latency", { exact: true })).toHaveCount(0)
  await expect(page.getByText("Sum of recorded turns")).toHaveCount(0)
  await expectHeaderLimitationInAbout(
    page,
    /^Session 88888888/,
    "Message content, hashes, and provider request ids are not part of this contract and are not shown.",
  )
  await expectNoAxeViolations(page)
})

test("live Sessions joins the agent, segments by status, and filters without inventing a total", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)

  await page.goto("/sessions")
  await waitForHydration(page)

  // The Agent column is the join against the agents read, not the session id.
  const row = page.locator("tr[data-session-row]")
  await expect(row.getByRole("link", { name: "Support Agent" })).toBeVisible()
  await expect(row.getByText("support-agent", { exact: true })).toBeVisible()

  // Segments come from the statuses that occur, with a per-page count.
  const tabs = page.getByRole("tab")
  await expect(tabs).toHaveCount(2)
  await expect(tabs.first()).toContainText("All sessions")
  await expect(page.getByRole("tab", { name: /Completed/ })).toBeVisible()
  await expect(page.getByText(/no organization total/)).toBeVisible()

  // The column control hides one of the optional columns, and Escape returns
  // focus to the trigger that opened it.
  const columnsTrigger = page.getByRole("button", { name: "Columns" })
  await columnsTrigger.click()
  await page.getByRole("switch", { name: "Extraction" }).click()
  await expect(page.getByRole("columnheader", { name: "Extracted to" })).toHaveCount(0)
  // The pointer is an index, not a ratio: no percentage is printed anywhere.
  await expect(page.getByText(/%\s*extracted/)).toHaveCount(0)
  await page.keyboard.press("Escape")
  await expect(columnsTrigger).toBeFocused()
  await expect(columnsTrigger).toHaveAttribute("aria-expanded", "false")

  // Search narrows on the external id, and an empty result says so.
  await page.getByRole("searchbox", { name: "Search sessions" }).fill("ext-a-1")
  await expect(row).toHaveCount(1)
  await page.getByRole("searchbox", { name: "Search sessions" }).fill("no-such-session")
  await expect(page.getByText("No sessions match these filters")).toBeVisible()
  await page.getByRole("button", { name: "Clear filters" }).click()
  await expect(row).toHaveCount(1)

  // The agent filter is server-side: it lands in the address bar and the read.
  await page.getByRole("combobox", { name: "Agent" }).selectOption({ label: "Support Agent · support-agent" })
  await expect(page).toHaveURL(/agent_id=33333333-3333-4333-8333-333333333333/)
  await expect
    .poll(async () => {
      const entries = await fetchFixtureRequests(page)
      return entries.filter((entry) => entry.path === "/v1/operator/sessions").length
    })
    .toBeGreaterThan(1)
  await expectNoAxeViolations(page)
})

test("live Sessions keeps the extraction pointer an index and prints no ratio", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)
  await page.setViewportSize({ width: 1440, height: 900 })

  await page.goto("/sessions")
  await waitForHydration(page)

  // The fixture session has one turn and stores pointer 0. That is the index of
  // turn 0 and also the column default: the contract cannot say which, so the
  // page states the index and claims no completion.
  const row = page.locator("tr[data-session-row]")
  await expect(page.getByRole("columnheader", { name: "Extracted to" })).toBeVisible()
  await expect(row.getByText("turn 0", { exact: true })).toBeVisible()
  await expect(row.getByText("0-based index", { exact: true })).toBeVisible()
  await expect(page.getByText(/\d+%\s+extracted/)).toHaveCount(0)
  await expectNoAxeViolations(page)

  await page.getByRole("link", { name: /88888888/ }).click()
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: /Session 88888888/ })).toBeVisible()
  await expect(page.getByText("Extracted to")).toBeVisible()
  await expect(page.getByText(/Zero-based turn index\. 0 is also the column default/)).toBeVisible()
  await expect(page.getByText(/\d+%\s+extracted/)).toHaveCount(0)
  await expectNoAxeViolations(page)
})

test("live Sessions retries the agents read on refresh", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)
  // The agents read fails once. Nothing is retained to hide it: the Agent column
  // has no names and the selector lists no agents.
  await failNextRead(page, "/v1/operator/agents")

  await page.goto("/sessions")
  await waitForHydration(page)
  const row = page.locator("tr[data-session-row]")
  await expect(row.getByText("Agent read unavailable")).toBeVisible()
  await expect(page.getByRole("combobox", { name: "Agent" }).locator("option")).toHaveCount(1)
  await expect(page.getByText("Name not in this agent page")).toHaveCount(0)

  // Before the fix this refresh only retried the sessions read, so the failed
  // join outlived the recovery and no session filter could retry it either.
  // Both reads are refreshed now.
  await page.getByRole("button", { name: "Refresh" }).click()
  await expect(row.getByRole("link", { name: "Support Agent" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "Agent" }).locator("option")).toHaveCount(2)
  await expect(page.getByText("Agent read unavailable")).toHaveCount(0)
})

test("live Sessions filters by an agent UUID outside the listed page", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)

  await page.goto("/sessions")
  await waitForHydration(page)
  const agentInput = page.getByRole("textbox", { name: "Agent ID" })

  // A partial id is refused with a stated reason, and nothing is requested.
  await agentInput.fill("bbbbbbbb")
  await page.getByRole("button", { name: "Filter by ID" }).click()
  await expect(page.getByRole("alert")).toContainText("full agent UUID")
  await expect(page).not.toHaveURL(/agent_id=/)

  // A full UUID becomes the server-side filter even though the agents page in
  // the fixture only lists the other agent.
  await agentInput.fill("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
  await page.getByRole("button", { name: "Filter by ID" }).click()
  await expect(page).toHaveURL(/agent_id=bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb/)
  await expect(page.getByRole("combobox", { name: "Agent" })).toHaveValue(
    "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  )
  await expect(page.getByRole("alert")).toHaveCount(0)
})

test("live Sessions is axe-clean at the narrow viewport, filters open", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)
  await page.setViewportSize({ width: 390, height: 844 })

  await page.goto("/sessions")
  await waitForHydration(page)
  await page.getByRole("button", { name: /Filters/ }).click()
  await expect(page.getByRole("textbox", { name: "Agent ID" })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("live Sessions returns from an agent to the filtered list it came from", async ({ page }) => {
  await resetFixtureApi(page)
  await seedOperatorCookies(page)

  await page.goto("/sessions?status=completed")
  await waitForHydration(page)
  await page.locator("tr[data-session-row]").getByRole("link", { name: "Support Agent" }).click()
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Support Agent" })).toBeVisible()
  // The back link follows the row it came from: the Sessions list, with its
  // filter, and labelled as such — not "Back to agents" pointing at /agents.
  const back = page.getByRole("link", { name: /Back to sessions/ })
  await expect(back).toHaveAttribute("href", "/sessions?status=completed")
  await back.click()
  await expect(page).toHaveURL(/\/sessions\?status=completed$/)
  await expect(page.getByRole("heading", { name: "Sessions", exact: true })).toBeVisible()
  // The request-scoped filter survived the round trip: the panel says the read
  // is limited to Completed sessions.
  await expect(page.getByText(/This link limits the read to/)).toBeVisible()
})
