import { expect, type Page } from "@playwright/test"

/**
 * A page-level limitation belongs in the header's About disclosure, not in a
 * sentence under the title.
 *
 * Both halves are asserted: no paragraph renders inside the header (the removed
 * caveat was one), the sentence is hidden while the disclosure is collapsed, and
 * it is visible once a reader opens it. A page that dropped the sentence without
 * carrying it into the disclosure fails on the last step.
 */
export async function expectHeaderLimitationInAbout(
  page: Page,
  title: string | RegExp,
  sentence: string,
): Promise<void> {
  const heading = page.getByRole("heading", {
    level: 1,
    name: title,
    ...(typeof title === "string" ? { exact: true } : {}),
  })
  const header = page.locator("header").filter({ has: heading }).first()

  await expect(heading).toBeVisible()
  await expect(header.locator("p:visible")).toHaveCount(0)

  const note = header.locator("details li").filter({ hasText: sentence })
  await expect(note).toHaveCount(1)
  await expect(note).toBeHidden()

  await header.locator("details summary").first().click()
  await expect(note).toBeVisible()
}
