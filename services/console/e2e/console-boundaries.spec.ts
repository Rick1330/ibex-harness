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
  await page.goto("/evidence")
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

test("memories fail closed without an operator API and never render fixtures", async ({ page }) => {
  await page.goto("/memories?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Memories", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Memory index unavailable" })).toBeVisible()
  await expect(page.getByText(/mem_d2f79fa2/)).toHaveCount(0)
  await expect(page.getByText(/Illustrative preview/)).toHaveCount(0)
  await expectNoAxeViolations(page)

  await page.goto("/memories/00000000-0000-4000-8000-000000000000?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Memory record unavailable" })).toBeVisible()
  await expectNoAxeViolations(page)
})

test("sessions fail closed without an operator API and never render fixtures", async ({ page }) => {
  await page.goto("/sessions?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Sessions", exact: true })).toBeVisible()
  await expect(page.getByRole("heading", { name: "Session index unavailable" })).toBeVisible()
  await expect(page.getByText(/ses_2481f0a2/)).toHaveCount(0)
  await expect(page.getByText(/Illustrative preview/)).toHaveCount(0)
  await expectNoAxeViolations(page)

  await page.goto("/sessions/00000000-0000-4000-8000-000000000000?demo=0")
  await waitForHydration(page)
  await expect(page.getByRole("heading", { name: "Session record unavailable" })).toBeVisible()
  await expectNoAxeViolations(page)
})
