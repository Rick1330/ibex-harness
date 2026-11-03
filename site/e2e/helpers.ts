import type { Page } from '@playwright/test'

/**
 * Wait until Nuxt has hydrated the page.
 *
 * SSR HTML is interactive-looking but Vue event handlers only work after
 * hydration. Under parallel browser load, `networkidle` can resolve before
 * hydration finishes, so click-based tests must wait for this marker.
 */
export async function waitHydrated(page: Page): Promise<void> {
  await page.waitForFunction(
    () => typeof (window as { useNuxtApp?: unknown }).useNuxtApp !== 'undefined',
    null,
    { timeout: 30_000 },
  )
}
