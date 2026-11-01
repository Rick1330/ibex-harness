import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("static surface status", () => {
  it("marks only the four validated reads as live", () => {
    const live = Object.values(SURFACES)
      .filter((surface) => surface.availability === "live")
      .map((surface) => surface.path)
      .sort()
    expect(live).toEqual(["/", "/agents", "/explore", "/platform"])
  })

  it("keeps the remaining fourteen surfaces in preview", () => {
    const preview = Object.values(SURFACES)
      .filter((surface) => surface.availability === "preview")
      .map((surface) => surface.path)
      .sort()
    expect(preview).toEqual([
      "/access",
      "/analytics",
      "/audit",
      "/budgets",
      "/directives",
      "/drift",
      "/evidence",
      "/incidents",
      "/mcp-tools",
      "/memories",
      "/policies",
      "/providers",
      "/sessions",
      "/settings",
    ])
  })

  it("does not retain billing as a product surface", () => {
    expect(Object.values(SURFACES).some((surface) => surface.path === "/billing")).toBe(false)
  })

  it("labels every preview contract and keeps domains explicit", () => {
    for (const surface of Object.values(SURFACES)) {
      expect(surface.contract.length, surface.path).toBeGreaterThan(0)
      expect(surface.question.length, surface.path).toBeGreaterThan(0)
      expect(surface.domain, surface.path).toMatch(/^D[1-6]$/)
    }
  })
})
