import { expect, test } from '@playwright/test'

const articles = [
  '/blog/proxy-before-memory',
  '/blog/memory-write-path',
  '/blog/context-assembly-budget',
]

test.describe('blog index', () => {
  test('featured card keeps its layout while hovered', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto('/blog')

    const cards = page.locator('a[href^="/blog/"]').filter({ has: page.locator('.blog-cover') })
    const featured = cards.first()
    await expect(featured).toBeVisible()

    const before = await featured.boundingBox()
    expect(before).not.toBeNull()
    expect(before!.width).toBeGreaterThan(800)

    const columnsBefore = await featured.evaluate(element =>
      getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length,
    )
    expect(columnsBefore).toBe(2)

    await featured.locator('.blog-cover').hover()
    // The hover animates the cover; wait for those transitions to settle
    // instead of a fixed sleep.
    await featured.locator('.blog-cover').evaluate(element =>
      Promise.all(element.getAnimations({ subtree: true }).map(animation => animation.finished.then(() => undefined))),
    )

    const after = await featured.boundingBox()
    expect(after).not.toBeNull()
    expect(Math.abs(after!.width - before!.width)).toBeLessThan(1)
    expect(Math.abs(after!.height - before!.height)).toBeLessThan(1)
    expect(after!.x).toBeCloseTo(before!.x, 0)
  })

  test('reduced motion disables hover transforms', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.setViewportSize({ width: 1440, height: 1000 })
    await page.goto('/blog')

    const featured = page.locator('a[href^="/blog/"]').filter({ has: page.locator('.blog-cover') }).first()
    const cover = featured.locator('.blog-cover').first()
    await cover.hover()

    await expect.poll(() => cover.evaluate(element => getComputedStyle(element).transform)).toBe('none')
  })

  test('mobile index does not overflow horizontally', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/blog')

    const featured = page.locator('a[href^="/blog/"]').filter({ has: page.locator('.blog-cover') }).first()
    await expect(featured).toBeVisible()

    const box = await featured.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.width).toBeLessThanOrEqual(390)

    const overflow = await page.evaluate(() =>
      document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    expect(overflow).toBeLessThanOrEqual(1)
  })

  test('every published article renders a heading', async ({ page }) => {
    for (const article of articles) {
      await page.goto(article)
      await expect(page.locator('h1').first()).toBeVisible()
    }
  })
})
