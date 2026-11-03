import { describe, expect, it } from "vitest"

import { resolveDemoMode } from "../app/lib/console-demo"

describe("resolveDemoMode", () => {
  it("never enables demo data in a production build", () => {
    expect(resolveDemoMode(false, "1")).toBe(false)
    expect(resolveDemoMode(false, undefined)).toBe(false)
    expect(resolveDemoMode(false, "0")).toBe(false)
  })

  it("defaults to demo in development and honors the opt-out", () => {
    expect(resolveDemoMode(true, undefined)).toBe(true)
    expect(resolveDemoMode(true, "1")).toBe(true)
    expect(resolveDemoMode(true, "0")).toBe(false)
  })
})
