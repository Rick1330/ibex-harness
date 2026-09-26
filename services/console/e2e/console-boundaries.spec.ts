import { createRequire } from "node:module"

import { expect, test } from "@playwright/test"

const require = createRequire(import.meta.url)

test("overview preserves shell and labels fixture data as preview", async ({ page }) => {
  await page.goto("/")
  await expect(page).toHaveURL(/\/dashboard$/)
  await expect(page.getByRole("status", { name: "Preview data" })).toContainText("Preview data")
  await expect(page.getByText("Overview", { exact: true }).first()).toBeVisible()
  await expect(page.getByText("Preview data — no live operator contract")).toBeVisible()
  await expect(page.getByText("Acme Corp").first()).toBeVisible()

  const overflow = await page.evaluate(() => {
    const width = document.documentElement.clientWidth
    return {
      pageWidth: document.documentElement.scrollWidth,
      viewportWidth: width,
      elements: [...document.querySelectorAll("body *")]
        .map((element) => ({
          tag: element.tagName,
          text: element.textContent?.trim().slice(0, 48),
          right: Math.round(element.getBoundingClientRect().right),
          className: typeof element.className === "string" ? element.className : "",
        }))
        .filter((element) => element.right > width + 1)
        .slice(0, 10),
    }
  })
  expect(overflow.pageWidth, JSON.stringify(overflow)).toBeLessThanOrEqual(overflow.viewportWidth)

  await page.keyboard.press("Tab")
  const focusIsVisible = await page.evaluate(() => {
    const active = document.activeElement
    if (!(active instanceof HTMLElement)) return false
    const style = getComputedStyle(active)
    return style.outlineStyle !== "none" || style.boxShadow !== "none"
  })
  expect(focusIsVisible).toBe(true)

  await page.addScriptTag({ path: require.resolve("axe-core") })
  const accessibility = await page.evaluate(async () => {
    const axe = (window as Window & { axe?: { run: (context: Document, options: object) => Promise<{ violations: Array<{ id: string; impact: string | null; help: string }> }> } }).axe
    if (!axe) throw new Error("axe-core did not load")
    const result = await axe.run(document, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"] },
    })
    return result.violations.map(({ id, impact, help }) => ({ id, impact, help }))
  })
  expect(accessibility).toEqual([])
})

test("mobile shell has no horizontal overflow and exposes the existing navigation", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto("/")
  await expect(page.getByText("Preview data — no live operator contract")).toBeVisible()
  const dimensions = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }))
  expect(dimensions.scroll, JSON.stringify(dimensions)).toBeLessThanOrEqual(dimensions.client)

  const toggle = page.getByRole("button", { name: "Toggle Sidebar" })
  await expect(toggle).toBeVisible()
  await toggle.click()
  await expect(page.getByText("Explore", { exact: true }).last()).toBeVisible()
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
})

test("nested D2 route rewrites to its safe deferred state with no fixture detail", async ({ page }) => {
  await page.goto("/dashboard/explore/t/trace_a91f7c")
  // Next Proxy rewrites internally; the user's requested URL remains stable.
  await expect(page).toHaveURL(/\/dashboard\/explore\/t\/trace_a91f7c$/)
  await expect(page.getByRole("heading", { name: "This Console surface is deferred" })).toBeVisible()
  await expect(page.getByText(/No domain fixtures or live data are served/)).toBeVisible()
  await expect(page.getByText("Directive support-refund")).toHaveCount(0)
})
