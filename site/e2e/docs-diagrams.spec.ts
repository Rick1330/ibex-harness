import { expect, test } from '@playwright/test'
import { waitHydrated } from './helpers'

// Docs pages ship mermaid code blocks through ProsePre → MermaidDiagram,
// which renders client-side after hydration and lazy-starts each diagram
// when it scrolls near the viewport. The contract: every diagram on the
// page settles — rendered SVG or the visible error state — and none is
// left in the "Rendering diagram" placeholder with no console error.
const pageWithDiagrams = '/docs/proxy/request-routing'

// The fixture page ships exactly two mermaid figures.
const expectedDiagramCount = 2

test.describe('docs page mermaid diagrams', () => {
  // The per-figure settled-state expectations below use their own 30s
  // windows; keep the test-level clock above them so a hang surfaces as
  // the assertion's timeout, never the test runner's.
  test.setTimeout(120_000)

  test('every mermaid diagram settles instead of rendering forever', async ({ page }) => {
    await page.goto(pageWithDiagrams)
    await waitHydrated(page)

    const figures = page.locator('figure.mermaid-figure')
    await expect(figures).toHaveCount(expectedDiagramCount)

    for (const figure of await figures.all()) {
      await figure.scrollIntoViewIfNeeded()
      const canvas = figure.locator('.mermaid-figure__canvas')
      // Settled outcome, scoped to this figure: the rendered SVG or the
      // visible error block — never an indefinite loading placeholder.
      const rendered = canvas.locator('.mermaid-figure__svg svg')
      const failed = canvas.locator('.mermaid-figure__error')
      await expect(rendered.or(failed)).toBeVisible({ timeout: 30_000 })
      await expect(canvas.locator('.mermaid-figure__loading')).toBeHidden({ timeout: 30_000 })
    }
  })

  test('the page\'s valid diagram sources render an svg', async ({ page }) => {
    await page.goto(pageWithDiagrams)
    await waitHydrated(page)

    const figures = page.locator('figure.mermaid-figure')
    await expect(figures).toHaveCount(expectedDiagramCount)

    for (const figure of await figures.all()) {
      await figure.scrollIntoViewIfNeeded()
      await expect(figure.locator('.mermaid-figure__svg svg')).toBeVisible({ timeout: 30_000 })
    }
  })

  test('surfaces a visible error when the mermaid library never finishes loading', async ({ page }) => {
    // Stall the mermaid library chunk regardless of its hashed name: while
    // its fetch never completes, every diagram on the page would wait on it
    // forever with no console error — exactly the indefinite-spinner
    // failure mode this suite exists to prevent.
    const mermaidChunkSignature = 'registerIconPacks'
    let heldMermaidChunkRequests = 0
    await page.route('**/_nuxt/*.js', async (route) => {
      const response = await route.fetch()
      const body = await response.text()
      if (body.includes(mermaidChunkSignature)) {
        heldMermaidChunkRequests += 1
        return // hold the route open
      }
      await route.fulfill({ response })
    })

    await page.goto(pageWithDiagrams)
    await waitHydrated(page)

    // MermaidDiagram only requests the library once a figure is near the
    // viewport; bring the first one in so the request — and with it the
    // stall — fires deterministically wherever the content sits on the page.
    await page.locator('figure.mermaid-figure').first().scrollIntoViewIfNeeded()

    // The stall must have engaged. If the signature ever stops matching
    // the library chunk (a mermaid upgrade renaming its API), nothing is
    // held, the page renders normally, and this discriminator fails the
    // test instead of letting it pass vacuously.
    await expect.poll(() => heldMermaidChunkRequests, { timeout: 10_000 }).toBeGreaterThanOrEqual(1)

    const figures = page.locator('figure.mermaid-figure')
    await expect(figures).toHaveCount(expectedDiagramCount)

    for (const figure of await figures.all()) {
      await figure.scrollIntoViewIfNeeded()
      const canvas = figure.locator('.mermaid-figure__canvas')
      // Under the held-chunk stall the error state is the only legitimate
      // settle for this test; a rendered svg here would mean the stall
      // never engaged.
      const failed = canvas.locator('.mermaid-figure__error')
      await expect(failed).toBeVisible({ timeout: 45_000 })
      await expect(canvas.locator('.mermaid-figure__loading')).toBeHidden({ timeout: 45_000 })
    }
  })
})
