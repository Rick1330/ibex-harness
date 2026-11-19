import { expect, test, type Browser, type BrowserContext, type Page } from "@playwright/test"
import {
  ACCESS_COOKIE,
  ORG_A,
  ORG_B,
  type TenantOrg,
  consoleOrigin,
  cookieValue,
  resetStandIn,
  signIn,
  standInRequests,
} from "./journeys"

/**
 * P2-07 — the two-tenant browser journey.
 *
 * Two browser contexts hold two sessions, each issued by `POST
 * /api/operator/session/login` for a different org. Each session reads its own
 * record, and then each is pointed at the other org's record id — an id that
 * exists in the stack and belongs to somebody else. The assertion is that the
 * console answers with a not-found verdict and renders none of the other org's
 * data, rather than serving the record because the URL asked for it.
 *
 * What this proves, and what it does not: the operator API here is the loopback
 * stand-in in `e2e/live-stack.mjs`, which resolves reads through the session's
 * org exactly as the tenant-scoped queries do. So this is the Console's
 * obligation: the BFF asks upstream with the session it was given, and the
 * browser fails closed on the refusal. The API's own isolation is covered by
 * `services/api/tests/integration/test_operator_route_tenancy.py` and the
 * per-resource RLS suites.
 *
 * A run against the real stack would need two provisioned orgs and a PAT for
 * each. There is no tenant-provisioning route (P1-40), and this host has no
 * database or object storage outside a container runtime, so the journey is
 * executed against the stand-in seam that `test:e2e:live` already uses rather
 * than skipped wholesale.
 */

async function openSession(browser: Browser, pat: string) {
  const context = await browser.newContext({
    baseURL: consoleOrigin,
    ignoreHTTPSErrors: true,
  })
  const page = await context.newPage()
  await signIn(page, pat)
  return { context, page }
}

async function expectOwnAccount(page: Page, org: TenantOrg): Promise<void> {
  await expect(page.getByText(new RegExp(`${org.name} · ${org.slug}`))).toBeVisible()
  await page.goto(`/agents/${org.agentId}`)
  await expect(page.getByRole("heading", { name: org.agentName })).toBeVisible()
}

async function expectRefused(
  page: Page,
  context: BrowserContext,
  org: TenantOrg,
): Promise<void> {
  await page.goto(`/agents/${org.agentId}`)

  // A not-found verdict, not a rendered record and not a silent fallback.
  await expect(page.getByRole("heading", { name: "Agent not found" })).toBeVisible()
  await expect(
    page.getByText(/does not exist in the current organization/),
  ).toBeVisible()
  // Not an authorization verdict either: the record is reported absent, which
  // is the same answer a nonexistent id gets and so leaks no existence.
  await expect(
    page.getByRole("heading", { name: "An operator session is required to read this agent" }),
  ).toHaveCount(0)
  await expect(page.getByRole("heading", { name: org.agentName })).toHaveCount(0)
  await expect(page.getByText(org.agentName, { exact: false })).toHaveCount(0)
  // The record id is in the address bar and therefore in the breadcrumb; the
  // slug only exists in the record, so its absence is the data assertion.
  await expect(page.getByText(org.agentSlug, { exact: false })).toHaveCount(0)

  // The refusal came from the operator API through this session, and the session
  // itself survived: a not-found is not a sign-out.
  expect(await cookieValue(context, ACCESS_COOKIE)).toBeTruthy()

  const response = await context.request.get(`/api/operator/agents/${org.agentId}`)
  expect(response.status()).toBe(404)
  expect(await response.text()).not.toContain(org.agentName)
}

test("org A's session cannot read org B's record, and the console says so", async ({
  browser,
  request,
}) => {
  test.setTimeout(120_000)
  await resetStandIn(request)

  const a = await openSession(browser, ORG_A.pat)
  const b = await openSession(browser, ORG_B.pat)

  // Two sessions, not one session used twice.
  const accessA = await cookieValue(a.context, ACCESS_COOKIE)
  const accessB = await cookieValue(b.context, ACCESS_COOKIE)
  expect(accessA).toBeTruthy()
  expect(accessB).toBeTruthy()
  expect(accessA).not.toBe(accessB)

  // Control: each session reads its own tenant, so a refusal below is not a
  // page that cannot render anything.
  await expectOwnAccount(a.page, ORG_A)
  await expectOwnAccount(b.page, ORG_B)

  // Org A pointed at org B's record.
  await expectRefused(a.page, a.context, ORG_B)
  // And the boundary is symmetric.
  await expectRefused(b.page, b.context, ORG_A)

  // Org A's session is intact after the refusal.
  await a.page.goto(`/agents/${ORG_A.agentId}`)
  await expect(a.page.getByRole("heading", { name: ORG_A.agentName })).toBeVisible()

  // Upstream evidence: each org's cookie reached the API, and the API answered
  // 404 for the other org's record id rather than serving it.
  const entries = await standInRequests(request)
  const refusedFor = (orgKey: string, agentId: string) =>
    entries.filter(
      (entry) =>
        entry.path === `/v1/operator/agents/${agentId}` &&
        entry.org === orgKey &&
        entry.status === 404,
    )

  expect(refusedFor("a", ORG_B.agentId).length).toBeGreaterThan(0)
  expect(refusedFor("b", ORG_A.agentId).length).toBeGreaterThan(0)
  expect(
    entries.filter(
      (entry) =>
        entry.path === `/v1/operator/agents/${ORG_B.agentId}` &&
        entry.org === "b" &&
        entry.status === 200,
    ).length,
    "org B could still read its own record",
  ).toBeGreaterThan(0)
})
