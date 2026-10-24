import { expect, test } from '@playwright/test'
import { waitHydrated } from './helpers'

test.describe('landing hero console', () => {
  test('switches between request, context, and trace panels', async ({ page }) => {
    await page.goto('/')
    await waitHydrated(page)

    const harness = page.locator('.harness-console')
    const request = harness.getByRole('tab', { name: /Request/ })
    const context = harness.getByRole('tab', { name: /Context/ })
    const trace = harness.getByRole('tab', { name: /Trace/ })

    await expect(request).toHaveAttribute('aria-selected', 'true')
    await expect(harness.getByText('/v1/chat/completions')).toBeVisible()

    await context.click()
    await expect(context).toHaveAttribute('aria-selected', 'true')
    await expect(harness.getByText('Assemble before forward')).toBeVisible()
    await expect(harness.getByText('Example allocation')).toBeVisible()

    await trace.click()
    await expect(trace).toHaveAttribute('aria-selected', 'true')
    await expect(harness.getByText('One request, inspectable')).toBeVisible()
    await expect(harness.getByText('trace.write')).toBeVisible()
  })

  test('supports keyboard navigation between tabs', async ({ page }) => {
    await page.goto('/')
    await waitHydrated(page)

    const harness = page.locator('.harness-console')
    const request = harness.getByRole('tab', { name: /Request/ })
    const context = harness.getByRole('tab', { name: /Context/ })
    const trace = harness.getByRole('tab', { name: /Trace/ })

    await request.focus()
    await request.press('ArrowRight')
    await expect(context).toBeFocused()

    await context.press('End')
    await expect(trace).toBeFocused()
  })

  test('code examples expose readable syntax highlighting and copy controls', async ({ page }) => {
    await page.goto('/')
    await waitHydrated(page)

    const code = page.locator('#drop-in .landing-code')
    const tabs = code.getByRole('tab')

    await expect(tabs.first()).toHaveAttribute('aria-selected', 'true')
    await expect(code.locator('.landing-code-token--command').first()).toHaveText('curl')
    await expect(code.locator('.landing-code-token--keyword').first()).toHaveText('POST')
    await expect(code.locator('.landing-code-token--string').first()).toBeVisible()
    await expect(code.getByRole('button', { name: /Copy curl example/ })).toBeVisible()

    await tabs.filter({ hasText: 'TypeScript' }).click()
    await expect(code.locator('.landing-code-token--keyword').first()).toHaveText('const')
    await expect(code.locator('.landing-code-token--function').first()).toHaveText('fetch')
  })

  test('copies the request example', async ({ page, context }) => {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await page.goto('/')
    await waitHydrated(page)

    const button = page.locator('.console-copy')
    await expect(button).toContainText('Copy')
    await button.click()
    await expect(button).toContainText('Copied')
    await expect(button).toHaveAttribute('aria-label', 'Request example copied')

    const copied = await page.evaluate(() => navigator.clipboard.readText())
    expect(copied).toContain('Authorization: Bearer $IBEX_TOKEN')
    expect(copied).toContain('X-IBEX-Agent-ID: agent_support')
  })

  test('landing field stays on the landing page only', async ({ page }) => {
    await page.goto('/')

    await expect(page.locator('body')).toHaveClass(/landing-page/)
    await expect(page.locator('header')).toHaveCSS('background-color', 'rgb(216, 255, 79)')

    await page.getByRole('link', { name: 'Docs' }).first().click()
    await expect(page).toHaveURL(/\/docs/)

    await expect(page.locator('body')).not.toHaveClass(/landing-page/)
    await expect(page.locator('header')).not.toHaveCSS('background-color', 'rgb(216, 255, 79)')
  })

  test('search is scoped to the landing page', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/')
    await waitHydrated(page)

    await page.getByRole('button', { name: /search/i }).first().click()

    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()

    const background = await dialog.evaluate(el => getComputedStyle(el).backgroundColor)
    expect(background).not.toBe('rgb(216, 255, 79)')

    await dialog.getByRole('textbox').fill('quickstart')
    await expect(dialog.getByText('Run it locally')).toBeVisible()
    await expect(dialog.getByText('Architecture overview')).toHaveCount(0)
  })

  test('mobile landing does not overflow horizontally', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')

    await expect(page.locator('.harness-console')).toBeVisible()

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)
  })
})
