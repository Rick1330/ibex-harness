import { expect, type Locator, type Page } from "@playwright/test"

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
  const heading = headingFor(page, title)
  const header = page.locator("header").filter({ has: heading }).first()

  await expect(heading).toBeVisible()
  await expect(header.locator("p:visible")).toHaveCount(0)

  const note = header.locator("details li").filter({ hasText: sentence })
  await expect(note).toHaveCount(1)
  await expect(note).toBeHidden()

  await aboutTrigger(header).click()
  await expect(note).toBeVisible()
}

/** Opens the header's About disclosure for the page whose `h1` matches `title`. */
export async function openAboutDisclosure(page: Page, title: string | RegExp): Promise<void> {
  await aboutTrigger(headerFor(page, title)).click()
}

/**
 * `toBeVisible()` is true for content clipped outside the viewport, so it cannot
 * prove a limitation is reachable on a phone.
 *
 * Below the `sm` breakpoint the About panel is fixed to the bottom edge and its
 * height follows its content. Before it was capped, the Evidence disclosure grew
 * to 775px and its top edge sat 187px above a 375x600 viewport, where the header,
 * verdict, and contract rows could not be scrolled into view at all. This asserts
 * geometry instead: the panel stays inside the viewport, and every note can be
 * scrolled into it through the panel's own scroll container.
 */
export async function expectAboutNotesReachable(
  page: Page,
  title: string | RegExp,
  sentence: string,
): Promise<void> {
  const header = headerFor(page, title)
  const panel = aboutPanel(header)

  await expect(panel).toBeVisible()
  await expect(header.locator("details li").filter({ hasText: sentence })).toHaveCount(1)
  await expectInsideViewport(page, panel, "the About panel")

  const notes = header.locator("details li")
  const count = await notes.count()
  expect(count).toBeGreaterThan(0)
  for (let index = 0; index < count; index += 1) {
    const note = notes.nth(index)
    await note.scrollIntoViewIfNeeded()
    await expectInsideViewport(page, note, `About note ${index + 1} of ${count}`)
  }

  // Scrolling the notes must scroll the panel, not drag the panel past an edge.
  await expectInsideViewport(page, panel, "the About panel after scrolling")
}

/** Escape closes the disclosure and returns focus to the trigger that opened it. */
export async function expectAboutDismissesWithEscape(page: Page, title: string | RegExp): Promise<void> {
  const header = headerFor(page, title)
  const panel = aboutPanel(header)
  const trigger = aboutTrigger(header)

  await expect(panel).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(panel).toBeHidden()
  await expect(trigger).toBeFocused()
}

function headingFor(page: Page, title: string | RegExp): Locator {
  return page.getByRole("heading", {
    level: 1,
    name: title,
    ...(typeof title === "string" ? { exact: true } : {}),
  })
}

function headerFor(page: Page, title: string | RegExp): Locator {
  return page.locator("header").filter({ has: headingFor(page, title) }).first()
}

function aboutTrigger(header: Locator): Locator {
  return header.locator("details summary").first()
}

function aboutPanel(header: Locator): Locator {
  return header.locator('details > div[role="dialog"]').first()
}

/**
 * A subpixel boundary is not a clipped boundary, so the comparison allows one
 * pixel of slack; anything larger means part of the element is off-screen.
 */
async function expectInsideViewport(page: Page, locator: Locator, label: string): Promise<void> {
  const box = await locator.boundingBox()
  const viewport = page.viewportSize()
  if (!box) throw new Error(`${label} has no bounding box`)
  if (!viewport) throw new Error(`${label} cannot be checked without a viewport size`)

  const slack = 1
  expect(box.x, `${label} left edge`).toBeGreaterThanOrEqual(-slack)
  expect(box.y, `${label} top edge`).toBeGreaterThanOrEqual(-slack)
  expect(box.x + box.width, `${label} right edge`).toBeLessThanOrEqual(viewport.width + slack)
  expect(box.y + box.height, `${label} bottom edge`).toBeLessThanOrEqual(viewport.height + slack)
}
