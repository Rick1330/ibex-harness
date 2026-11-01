import { createRequire } from "node:module"
import { expect, test } from "@playwright/test"

const require = createRequire(import.meta.url)

async function waitForHydration(page: import("@playwright/test").Page): Promise<void> {
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

async function expectNoAxeViolations(page: import("@playwright/test").Page): Promise<void> {
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

test("overview fails closed without mock data and preserves the shell", async ({ page }) => {
  await page.goto("/?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Overview", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: /Organization snapshot unavailable/ })).toBeVisible()
  await expect(page.getByText("No counts are invented for the gap.")).toBeVisible()
  await expect(page.getByText("Acme Corp")).toHaveCount(0)
  await expect(page.getByText("1,284,092")).toHaveCount(0)
  await expect(page.locator('[data-tone="attention"]').first()).toBeVisible()
  await expectNoAxeViolations(page)
})

test("platform fails closed without live data and keeps its full layout", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/platform?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Platform", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: /Platform snapshot unavailable/ })).toBeVisible()
  await expect(page.getByText("No dependency snapshot was read")).toBeVisible()
  await expect(page.getByText("No dependency checks reported")).toHaveCount(0)
  await expect(page.getByText(/Sample data/)).toHaveCount(0)
  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scroll, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.client)
  await expectNoAxeViolations(page)
})

test("legacy dashboard paths redirect to the approved top-level routes", async ({ page }) => {
  await page.goto("/dashboard")
  await expect(page).toHaveURL(/\/$/)
  await page.goto("/dashboard/explore?limit=25&status=ok")
  await expect(page).toHaveURL(/\/explore\?limit=25&status=ok$/)
  await page.goto("/dashboard/analytics")
  await expect(page).toHaveURL(/\/analytics$/)
  await page.goto("/dashboard/billing")
  await expect(page).toHaveURL(/\/budgets$/)
  await page.goto("/dashboard/memories/mem_legacy_1")
  await expect(page).toHaveURL(/\/memories\/mem_legacy_1$/)
  await page.goto("/dashboard/agents/agt_legacy_1")
  await expect(page).toHaveURL(/\/agents\/agt_legacy_1$/)
  await page.goto("/dashboard/policies/rules/rule_legacy_1")
  await expect(page).toHaveURL(/\/policies\/rules\/rule_legacy_1$/)
})

test("unknown legacy dashboard paths fail closed with 404", async ({ page }) => {
  const response = await page.goto("/dashboard/not-a-surface")
  expect(response?.status()).toBe(404)
  const nested = await page.goto("/dashboard/settings/not-a-section")
  expect(nested?.status()).toBe(404)
  const overview = await page.goto("/dashboard/overview/not-a-view")
  expect(overview?.status()).toBe(404)
})

test("sessions list uses one provenance chip and one About contract", async ({ page }) => {
  await page.goto("/sessions")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Sessions", exact: true })).toBeVisible()
  await expect(
    page.getByText("What happened across an agent session, turn by turn, and how complete the recorded evidence is."),
  ).toBeVisible()
  await expect(page.getByRole("button", { name: "About this data: illustrative" })).toHaveCount(1)
  await expect(page.getByText("Illustrative data below is not live organization data.")).toHaveCount(0)

  await page.getByRole("button", { name: "About this data: illustrative" }).click()
  const about = page.getByRole("dialog", { name: "About this data" })
  await expect(about).toBeVisible()
  await expect(about).toContainText("Read-only console")
  await expect(about).toContainText("operator.sessions.list.v1")
  await page.keyboard.press("Escape")
  await expect(about).toBeHidden()
  await expectNoAxeViolations(page)
})

test("session detail aggregates every turn and keeps the trace evidence intact", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/sessions/ses_2481f0a2?turn=1&panel=trace")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Refund policy escalation", exact: true })).toBeVisible()

  const totals = page.getByRole("region", { name: "Session totals" })
  await expect(totals.getByText("Agent time")).toBeVisible()
  await expect(totals.getByText("1.18 s")).toBeVisible()
  await expect(totals.getByText("Wall time")).toBeVisible()
  await expect(totals.getByText("14.05 s")).toBeVisible()
  await expect(totals.getByText("2,966 in · 441 out")).toBeVisible()
  await expect(totals.getByText("$0.090")).toBeVisible()

  const inspector = page.getByRole("complementary", { name: "Turn inspector" })
  await expect(inspector.getByText("Turn 1 of 4")).toBeVisible()
  await expect(inspector.getByRole("tab", { name: /^Trace/ })).toHaveAttribute("aria-selected", "true")
  await expect(inspector.getByText("60 ms in tools")).toBeVisible()
  await expect(inspector.getByText("tool.refund.preview", { exact: true }).first()).toBeVisible()

  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scroll, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.client)

  await expectNoAxeViolations(page)
})

test("session detail keeps turn and panel state in the URL and on reload", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/sessions/ses_2481f0a2?turn=2&panel=policy")
  await waitForHydration(page)

  const inspector = page.getByRole("complementary", { name: "Turn inspector" })
  await expect(inspector.getByText("Turn 2 of 4")).toBeVisible()
  await expect(inspector.getByRole("tab", { name: /^Policy/ })).toHaveAttribute("aria-selected", "true")

  await page.reload()
  await waitForHydration(page)
  await expect(inspector.getByText("Turn 2 of 4")).toBeVisible()
  await expect(inspector.getByRole("tab", { name: /^Policy/ })).toHaveAttribute("aria-selected", "true")

  await page.keyboard.press("j")
  await expect(page).toHaveURL(/turn=3/)
  await expect(page).toHaveURL(/panel=policy/)
  await expect(inspector.getByText("Turn 3 of 4")).toBeVisible()

  await page.keyboard.press("5")
  await expect(page).toHaveURL(/panel=drift/)
  await expect(inspector.getByRole("tab", { name: /^Drift/ })).toHaveAttribute("aria-selected", "true")
  await expect(inspector.getByText(/Drift advisory on this turn/)).toBeVisible()

  await page.keyboard.press("?")
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeVisible()
  await page.keyboard.press("?")
  await expect(page.getByRole("dialog", { name: "Keyboard shortcuts" })).toBeHidden()
})

test("session detail first turn starts near the content top at the reference viewport", async ({ page }) => {
  await page.setViewportSize({ width: 1757, height: 1410 })
  await page.goto("/sessions/ses_2481f0a2?turn=1&panel=trace")
  await waitForHydration(page)

  const offset = await page.evaluate(() => {
    const turn = document.querySelector('[data-turn-index="1"]')
    const content = document.querySelector("#console-main")?.firstElementChild
    if (!turn || !content) return Number.POSITIVE_INFINITY
    return turn.getBoundingClientRect().top - content.getBoundingClientRect().top
  })
  expect(offset).toBeLessThanOrEqual(300)

  await page.evaluate(() => window.scrollTo(0, 1400))
  await page.waitForTimeout(300)
  const sticky = await page.evaluate(() => {
    const outline = document.querySelector(".ix-outline-full")
    const inspector = document.querySelector("aside.ix-inspector")
    return {
      outlineTop: outline?.getBoundingClientRect().top ?? -1,
      inspectorTop: inspector?.getBoundingClientRect().top ?? -1,
    }
  })
  expect(sticky.outlineTop).toBeGreaterThan(48)
  expect(sticky.outlineTop).toBeLessThan(96)
  expect(sticky.inspectorTop).toBeLessThanOrEqual(sticky.outlineTop + 1)
})

test("session detail opens the inspector as a full-screen sheet on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/sessions/ses_2481f0a2?turn=1&panel=trace")
  await waitForHydration(page)

  const fab = page.locator(".ix-inspect-fab")
  await expect(fab).toBeVisible()
  await fab.click()

  const sheet = page.getByRole("dialog", { name: "Turn inspector" })
  await expect(sheet).toBeVisible()
  await expect(sheet.getByRole("tab")).toHaveCount(6)
  for (const label of ["Trace", "Memories", "Directive", "Policy", "Drift", "Privacy"]) {
    await expect(sheet.getByRole("tab", { name: new RegExp(`^${label}`) })).toBeVisible()
  }

  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scroll, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.client)

  await sheet.getByRole("button", { name: "Close inspector" }).click()
  await expect(sheet).toBeHidden()
  await expectNoAxeViolations(page)
})

test("memories keep safety state explicit and filter locally", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/memories")
  await expect(page.getByRole("heading", { name: "Memories", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "About this data: illustrative" })).toBeVisible()
  await page.locator("summary[aria-label='About this data']").click()
  const aboutData = page.getByRole("dialog", { name: "About this data" })
  await expect(aboutData).toBeVisible()
  await expect(aboutData.getByText(/26 illustrative memories across 9 agents/)).toBeVisible()
  await page.locator("summary[aria-label='About this data']").click()
  await expect(aboutData).toBeHidden()
  const table = page.locator('[aria-label="Memory table"]')
  await expect(table.getByText("Quarantined", { exact: true }).first()).toBeVisible()
  const dimensions = await table.evaluate((element) => ({
    client: element.clientWidth,
    scroll: element.scrollWidth,
  }))
  // The redesigned table fits its card at the reference viewport (rounding tolerance).
  expect(dimensions.scroll - dimensions.client).toBeLessThanOrEqual(2)

  await waitForHydration(page)
  const searchbox = page.getByRole("searchbox", { name: "Search memories" })
  await expect(async () => {
    await searchbox.fill("Europe/Berlin")
    await expect(page.getByText("Showing 1 of 26")).toBeVisible({ timeout: 500 })
  }).toPass({ timeout: 10_000 })
  await expect(searchbox).toHaveValue("Europe/Berlin")
  await expect(table.getByRole("link", { name: "Open mem_d2f79fa2" })).toBeVisible()
  await expect(table.getByRole("link", { name: "Open mem_77b031" })).toHaveCount(0)

  const pageDimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(pageDimensions.scroll, JSON.stringify(pageDimensions)).toBeLessThanOrEqual(pageDimensions.client)
  await expectNoAxeViolations(page)
})

test("memory detail preserves list filters, gates content, and exposes history", async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/memories?view=review&status=quarantined")
  await waitForHydration(page)
  const row = page.getByRole("link", { name: "Open mem_9c02a741" })
  await expect(row).toBeVisible()
  await row.click()
  await expect(page).toHaveURL(/\/memories\/mem_9c02a741\?return=/)
  await expect(page.getByRole("heading", { name: "Quarantined refund instruction", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "About this data: illustrative" })).toBeVisible()
  await expect(page.getByText("Quarantined · human review required").first()).toBeVisible()
  await expect(page.getByText("Privileged content gated", { exact: true })).toBeVisible()
  await page.getByRole("tab", { name: "History" }).click()
  await expect(page.getByRole("tab", { name: "History" })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByText("History timeline", { exact: true })).toBeVisible()
  await expect(page.getByText("Danger zone", { exact: true })).toBeVisible()
  const back = page.getByRole("link", { name: "Back to memories" })
  await expect(back).toHaveAttribute("href", "/memories?view=review&status=quarantined")
  await expectNoAxeViolations(page)

  await back.click()
  await expect(page).toHaveURL(/\/memories\?view=review&status=quarantined$/)
  await expect(page.getByText("Showing 2 of 26")).toBeVisible()

  await page.goto("/memories/mem_3f71d2aa")
  await expect(page.getByRole("heading", { name: "Tombstoned deletion record", exact: true })).toBeVisible()
  await expect(page.getByText("Content removed under a deletion request").first()).toBeVisible()
  await expect(page.getByText("Deletion receipt", { exact: true })).toBeVisible()
  await expect(page.getByText(/del_01J9Z6P2K8Q4V7M3/).first()).toBeVisible()
  await expectNoAxeViolations(page)
})

test("explore keeps an invalid query explicit and does not fetch data", async ({ page }) => {
  await page.goto("/explore?unknown=1")
  await expect(page.getByText("Invalid query")).toBeVisible()
  await expect(page.getByText(/Unknown query field: unknown/).first()).toBeVisible()
  await expect(page.getByText("No mock values are substituted.")).toHaveCount(0)
})

test("command menu searches and navigates", async ({ page }) => {
  await page.goto("/")
  await waitForHydration(page)
  const dialog = page.getByRole("dialog", { name: "Search console" })
  await expect(async () => {
    if (!(await dialog.isVisible())) {
      await page.getByRole("button", { name: "Search pages and surfaces" }).click()
    }
    await expect(dialog).toBeVisible({ timeout: 500 })
  }).toPass({ timeout: 10_000 })
  await expectNoAxeViolations(page)
  await dialog.getByRole("searchbox", { name: "Search pages" }).fill("platform")
  await dialog.getByRole("button", { name: /Platform/ }).click()
  await expect(page).toHaveURL(/\/platform$/)
  await expect(page.getByRole("heading", { name: "Platform", exact: true })).toBeVisible()
})

test("mobile shell has no horizontal overflow and exposes navigation", async ({ page }) => {
  const runtimeErrors: string[] = []
  const isBenignRuntimeError = (text: string) =>
    text.includes("about:blank") || text.includes("favicon")
  page.on("console", (message) => {
    if (message.type() === "error" && !isBenignRuntimeError(message.text())) runtimeErrors.push(message.text())
  })
  page.on("pageerror", (error) => {
    if (!isBenignRuntimeError(error.message)) runtimeErrors.push(error.message)
  })
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/")
  await waitForHydration(page)
  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scroll, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.client)

  const toggle = page.getByRole("button", { name: "Toggle Sidebar" })
  await expect(toggle).toBeVisible()
  const exploreLink = page.getByRole("link", { name: "Explore" }).last()
  await expect(async () => {
    if (!(await exploreLink.isVisible())) {
      await toggle.click()
    }
    await expect(exploreLink).toBeVisible({ timeout: 500 })
  }).toPass({ timeout: 10_000 })
  await expectNoAxeViolations(page)
  expect(runtimeErrors).toEqual([])
})

test("access keeps its tab, search, and drawer in the URL", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/access")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Access", exact: true })).toBeVisible()
  await expect(page.getByRole("button", { name: "About this data: illustrative" })).toHaveCount(1)
  await expect(page.getByRole("button", { name: "Create key" })).toBeDisabled()

  await page.getByRole("tab", { name: /Members/ }).click()
  await expect(page).toHaveURL(/tab=members/)
  await page.reload()
  await waitForHydration(page)
  await expect(page.getByRole("tab", { selected: true })).toContainText("Members")

  const search = page.getByRole("searchbox", { name: "Search members" })
  await search.fill("Avery")
  await expect(page).toHaveURL(/q=Avery/)
  await expect(page.getByText("1 member", { exact: true })).toBeVisible()

  await search.fill("")
  await page.getByRole("tab", { name: /Keys/ }).click()
  await page.locator('[data-access-row="key_9f2a"]').click()
  await expect(page).toHaveURL(/item=key_9f2a/)
  await expect(page.getByRole("dialog").first()).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(page).toHaveURL(/\/access$/)
  await expectNoAxeViolations(page)
})

test("settings keeps its category and section in the URL and the keyboard", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/settings?section=retention")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible()
  await expect(page.getByRole("tab", { name: "Data" })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { name: "Retention", exact: true })).toBeVisible()

  await page.keyboard.press("]")
  await expect(page).toHaveURL(/\/settings$/)
  await expect(page.getByRole("tab", { name: "General" })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { name: "Organization", exact: true })).toBeVisible()

  await page.keyboard.press("[")
  await expect(page).toHaveURL(/section=retention/)
  await expect(page.getByRole("tab", { name: "Data" })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { name: "Retention", exact: true })).toBeVisible()

  await page.goto("/settings?section=privacy")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Privacy and redaction", exact: true })).toBeVisible()
  await expect(page.getByText("Presidio · enabled", { exact: true })).toBeVisible()
  await expect(page.getByText("Active legal holds", { exact: true })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("agent surfaces fail closed without horizontal overflow on narrow viewports", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/agents")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Agents", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Agent inventory unavailable" })).toBeVisible()

  const listDimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(listDimensions.scroll, JSON.stringify(listDimensions)).toBeLessThanOrEqual(listDimensions.client)
  await expectNoAxeViolations(page)

  await page.goto("/agents/33333333-3333-4333-8333-333333333333")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Agent record unavailable" })).toBeVisible()
  const detailDimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(detailDimensions.scroll, JSON.stringify(detailDimensions)).toBeLessThanOrEqual(detailDimensions.client)
  await expectNoAxeViolations(page)
})

test("directives stay a list, filter in the URL, and open a route", async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/directives")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Directives", exact: true })).toBeVisible()
  const table = page.locator('[aria-label="Directive table"]')
  await expect(table).toBeVisible()
  await expect(page.locator("tr[data-directive-row]")).toHaveCount(4)
  // Visiting the list must never auto-open a record.
  await expect(page.getByRole("dialog", { name: "Directive quick look" })).toHaveCount(0)

  const search = page.getByRole("searchbox", { name: "Search directives" })
  await search.fill("billing")
  await expect(page).toHaveURL(/[?&]q=billing/)
  // "billing" appears in both Billing assistant and Support triage (billing impact check).
  await expect(page.getByText("Showing 2 of 4")).toBeVisible()
  await expect(page.locator("tr[data-directive-row]")).toHaveCount(2)

  await table.getByRole("button", { name: "Open Billing assistant" }).click()
  await expect(page).toHaveURL(/\/directives\/dir_billing_assistant/)
  await expect(page.getByRole("heading", { name: "Billing assistant", exact: true })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("directive detail keeps six tab states in the URL and reports candidate facts", async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/directives/dir_support_triage")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Support triage", exact: true })).toBeVisible()
  await expect(page.getByText(/Live:\s*v13/)).toBeVisible()
  await expect(page.getByText(/Candidate:\s*v14/)).toBeVisible()

  const tabs = page.getByRole("tablist", { name: "Directive views" }).getByRole("tab")
  await expect(tabs).toHaveCount(6)
  for (const label of ["Overview", "Versions", "Diff", "Promotion", "Usage", "Audit"]) {
    await expect(page.getByRole("tab", { name: new RegExp(`^${label}`) })).toBeVisible()
  }

  await page.getByRole("tab", { name: /^Diff/ }).click()
  await expect(page).toHaveURL(/tab=diff/)
  await expect(page.getByRole("tab", { name: /^Diff/ })).toHaveAttribute("aria-selected", "true")
  // The diff defaults to live → candidate.
  await expect(page.getByText("v13 → v14")).toBeVisible()

  await page.reload()
  await waitForHydration(page)
  await expect(page.getByRole("tab", { name: /^Diff/ })).toHaveAttribute("aria-selected", "true")

  await page.getByRole("tab", { name: /^Promotion/ }).click()
  await expect(page).toHaveURL(/tab=promotion/)
  // The promotion path marks each step and highlights approval while it waits.
  const path = page.getByRole("region", { name: "Promotion path" })
  await expect(path).toBeVisible()
  const steps = path.getByRole("listitem")
  await expect(steps).toHaveCount(5)
  for (const label of ["Draft", "Submitted", "Checks", "Approval", "Live"]) {
    await expect(path.getByText(new RegExp(`^${label}`))).toBeVisible()
  }
  await expect(path.locator('[aria-current="step"]')).toContainText("Approval")
  await expect(path.getByText("0 of 1 approvals recorded")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Promotion readiness" })).toBeVisible()
  await expect(page.getByText("No failed checks")).toBeVisible()
  await expect(page.getByRole("heading", { name: "Rollback plan" })).toBeVisible()
  await expect(page.getByText(/Target\s*v12/)).toBeVisible()
  // Three of four candidate checks pass; approval is still pending.
  await expect(page.getByText("3/4 passed").first()).toBeVisible()
  await expect(page.getByText("Requires a privileged write contract").first()).toBeVisible()
  await expectNoAxeViolations(page)
})

test("policies expose the current snapshot, history, changes, raw data, and time travel", async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/policies")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Policies", exact: true })).toBeVisible()
  await expect(page.getByText("Current", { exact: true }).first()).toBeVisible()
  await expect(page.getByRole("tab", { name: /Rules in force/ })).toBeVisible()
  await expect(page.getByRole("row", { name: "Open Refund approval threshold" })).toBeVisible()

  await page.getByRole("tab", { name: /Snapshots/ }).click()
  await expect(page.getByRole("link", { name: "Open snapshot pol_2026_10_27_03" })).toBeVisible()

  await page.goto("/policies/snapshots/pol_2026_10_27_03")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "What changed" })).toBeVisible()
  await expect(page.getByText(/2 rules changed/)).toBeVisible()
  const rawPre = page.locator('[aria-label="Raw snapshot JSON"]')
  await expect(async () => {
    if (!(await rawPre.isVisible())) await page.getByRole("tab", { name: /^Raw/ }).click()
    await expect(rawPre).toBeVisible({ timeout: 500 })
  }).toPass({ timeout: 10_000 })
  await expect(rawPre).toContainText("budget.ceiling")

  await page.goto("/policies/resolve")
  await waitForHydration(page)
  await page.getByLabel("Run ID").fill("run_77b031")
  await page.getByRole("button", { name: "Resolve" }).click()
  await expect(page).toHaveURL(/\/policies\/resolve\?run=run_77b031/)
  await expect(page.getByText(/run_77b031/).first()).toBeVisible()
  await expectNoAxeViolations(page)
})

test("policy rule detail keeps four tab states in the URL and gates missing data", async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/policies/rules/tools.approval")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "Refund approval threshold", exact: true })).toBeVisible()
  const tabs = page.getByRole("tablist", { name: "Policy rule views" }).getByRole("tab")
  await expect(tabs).toHaveCount(4)
  for (const label of ["Overview", "Fires", "History", "Where it applies"]) {
    await expect(page.getByRole("tab", { name: new RegExp(`^${label}`) })).toBeVisible()
  }

  await page.getByRole("tab", { name: /^History/ }).click()
  await expect(page).toHaveURL(/tab=history/)
  await page.reload()
  await waitForHydration(page)
  await expect(page.getByRole("tab", { name: /^History/ })).toHaveAttribute("aria-selected", "true")

  await page.getByRole("tab", { name: /^Fires/ }).click()
  await expect(page).toHaveURL(/tab=fires/)
  await expect(page.getByRole("table", { name: "Runs that fired this rule" })).toBeVisible()
  await expect(page.getByText(/partial provenance/).first()).toBeVisible()

  // A rule without precedence data keeps the scope tab explicit.
  await page.goto("/policies/rules/budget.ceiling?tab=scope")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Scope" })).toBeVisible()
  await expect(page.getByText("Runtime precedence")).toBeVisible()
  await expect(page.getByText("Not reported yet")).toBeVisible()
  await expectNoAxeViolations(page)
})

test("govern surfaces stay readable without horizontal overflow on mobile", async ({ page }) => {
  test.setTimeout(60_000)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/directives")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Directives", exact: true })).toBeVisible()
  await expect(page.locator('table[aria-label="Directive table"]')).toBeHidden()
  await expect(page.getByRole("button", { name: "Open Support triage" }).first()).toBeVisible()
  const directiveDimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(directiveDimensions.scroll, JSON.stringify(directiveDimensions)).toBeLessThanOrEqual(directiveDimensions.client)
  await expectNoAxeViolations(page)

  await page.goto("/policies")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Policies", exact: true })).toBeVisible()
  await expect(page.locator('table[aria-label="Policy rules in force"]')).toBeHidden()
  await expect(page.getByRole("article", { name: "Open policy rule Refund approval threshold" })).toBeVisible()
  const policyDimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(policyDimensions.scroll, JSON.stringify(policyDimensions)).toBeLessThanOrEqual(policyDimensions.client)
  await expectNoAxeViolations(page)

  await page.goto("/directives/dir_support_triage?tab=promotion")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Support triage", exact: true })).toBeVisible()
  const detailDimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(detailDimensions.scroll, JSON.stringify(detailDimensions)).toBeLessThanOrEqual(detailDimensions.client)
  await expectNoAxeViolations(page)
})

test("memory evidence exposes thresholded PII findings and redaction state", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/memories/mem_9e13c2ab")
  await waitForHydration(page)

  await page.getByRole("tab", { name: /Evidence/ }).click()
  await expect(page.getByRole("heading", { name: "PII detection and redaction", exact: true })).toBeVisible()
  await expect(page.getByText("Redacted before storage", { exact: true })).toBeVisible()
  await expect(page.getByRole("cell", { name: "Credit Card", exact: true })).toBeVisible()
  await expect(page.getByRole("cell", { name: "Phone Number", exact: true })).toBeVisible()
  await expect(page.getByRole("link", { name: /content\.pii/ })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("session privacy tab reports capture mode, redaction proof, and removed fields", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/sessions/ses_18bd3e09?turn=1&panel=privacy")
  await waitForHydration(page)

  await expect(page.getByRole("heading", { name: "PII redaction review", exact: true })).toBeVisible()
  await expect(page.getByText("PII findings", { exact: true })).toBeVisible()
  await expect(page.getByText("Removed before storage", { exact: true })).toBeVisible()
  await expect(page.getByText("session-metadata-allowlist/v1", { exact: true })).toBeVisible()
  await expect(page.getByText("Redacted is not the same as complete.")).toBeVisible()
  await expectNoAxeViolations(page)
})

test("evidence redaction tab lists sanitizers, proof versions, and removed fields", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/evidence?tab=redaction")
  await waitForHydration(page)

  await expect(page.getByRole("tab", { name: /Redaction/ })).toHaveAttribute("aria-selected", "true")
  await expect(page.getByRole("heading", { name: "Session evidence sanitizer", exact: true })).toBeVisible()
  await expect(page.getByText("Memory PII pipeline", { exact: true })).toBeVisible()
  await expect(page.getByText("span.attributes", { exact: true })).toBeVisible()
  await expect(page.getByRole("cell", { name: "session-metadata-allowlist/v1" }).first()).toBeVisible()
  await expectNoAxeViolations(page)
})

test("audit list shows redaction counts and the event explains the PII rule", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/audit")
  await waitForHydration(page)

  await expect(page.getByRole("columnheader", { name: /Redactions/ })).toBeVisible()
  await page.goto("/audit/events/evt_61a0c5")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: /retention job tombstoned memory/i })).toBeVisible()
  await page.getByRole("tab", { name: "Request" }).click()
  await expect(page.getByText("source_excerpt", { exact: true })).toBeVisible()
  await expect(page.getByText("content.pii", { exact: true })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("sidebar shows the core lifecycle and hides the platform tier by default", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/")
  await waitForHydration(page)

  const sidebar = page.locator(".console-sidebar")
  for (const label of ["Overview", "Agents", "Sessions", "Memories", "Evidence", "Directives", "Policies", "Explore", "Platform", "Settings"]) {
    await expect(sidebar.getByRole("link", { name: label, exact: true })).toBeVisible()
  }
  await expect(sidebar.getByRole("link", { name: "Incidents", exact: true })).toBeHidden()
  await expect(sidebar.getByText("Platform tier", { exact: true })).toBeVisible()

  await sidebar.getByText("Platform tier", { exact: true }).click()
  await expect(sidebar.getByRole("link", { name: "Incidents", exact: true })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("preview surfaces carry a persistent illustrative banner and live surfaces do not", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/sessions")
  await waitForHydration(page)

  const banner = page.getByRole("note", { name: "Illustrative preview" })
  await expect(banner).toBeVisible()
  await expect(banner).toContainText("No live operator data is rendered")
  await expectNoAxeViolations(page)

  await page.goto("/")
  await waitForHydration(page)
  await expect(page.getByRole("note", { name: "Illustrative preview" })).toHaveCount(0)

  await page.goto("/incidents")
  await waitForHydration(page)
  await expect(page.getByRole("note", { name: "Illustrative preview" })).toContainText(
    "Platform tier: this surface is not part of the memory/context console",
  )
})

test("command menu searches the core lifecycle only", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto("/")
  await waitForHydration(page)

  await page.keyboard.press("Control+k")
  const dialog = page.getByRole("dialog", { name: "Search console" })
  await expect(dialog).toBeVisible()

  await dialog.getByRole("searchbox").fill("incident")
  await expect(dialog.getByText("No matching pages.")).toBeVisible()

  await dialog.getByRole("searchbox").fill("memories")
  await expect(dialog.getByRole("button", { name: /Memories/ })).toBeVisible()
})

test("agents fail closed without an operator API and never render fixtures", async ({ page }) => {
  await page.goto("/agents?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Agents", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Agent inventory unavailable" })).toBeVisible()
  await expect(page.getByText("Support Agent")).toHaveCount(0)
  await expect(page.getByText(/Illustrative preview/)).toHaveCount(0)

  // An unsupported query is replaced with the supported state when a filter changes.
  await page.getByRole("searchbox", { name: "Search" }).fill("support")
  await expect(page).toHaveURL(/search=support/)
  await expect(page).not.toHaveURL(/demo=0/)
  await expectNoAxeViolations(page)
})
