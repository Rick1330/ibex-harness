import { describe, expect, it } from "vitest"

import { loginHref, safeLoginNext } from "../app/lib/navigation"

/**
 * The sign-in link a session refusal renders. `safeLoginNext` decides what is
 * an acceptable return target, so these cases are about the URL the link
 * produces and the fact that it cannot be turned into an open redirect.
 */
describe("session-refusal sign-in link", () => {
  it("sends the overview to the login page without a redundant return target", () => {
    expect(loginHref("/")).toBe("/login")
    expect(loginHref()).toBe("/login")
  })

  it("returns the refused surface, including its query", () => {
    expect(loginHref("/agents?search=support&limit=25")).toBe(
      "/login?next=%2Fagents%3Fsearch%3Dsupport%26limit%3D25",
    )
    expect(loginHref("/memories/44444444-4444-4444-8444-444444444444")).toBe(
      "/login?next=%2Fmemories%2F44444444-4444-4444-8444-444444444444",
    )
  })

  it("round-trips the target the login page will accept", () => {
    const href = loginHref("/explore?limit=10&status=ok")
    const next = new URL(href, "https://console.example").searchParams.get("next")
    expect(next).toBe("/explore?limit=10&status=ok")
    expect(safeLoginNext(next)).toBe("/explore?limit=10&status=ok")
  })

  it("burns down to the overview for anything the login page would refuse", () => {
    for (const target of [
      "https://evil.example/steal",
      "//evil.example/steal",
      "javascript:alert(1)",
      "/api/operator/overview",
      "/login?next=/explore",
      "/logout",
      "/_nuxt/app.js",
      "/../../etc/passwd",
      "/explore\n/evil",
    ]) {
      expect(loginHref(target), target).toBe("/login")
    }
  })

  it("accepts the first value when the route repeats the query field", () => {
    expect(loginHref(["/agents", "/explore"])).toBe("/login?next=%2Fagents")
    expect(loginHref(["//evil.example", "/agents"])).toBe("/login")
  })
})
