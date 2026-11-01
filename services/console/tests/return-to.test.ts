import { describe, expect, it } from "vitest"

import { safeExploreReturn } from "../app/lib/return-to"

describe("explore return target", () => {
  it("accepts only local explore paths", () => {
    expect(safeExploreReturn("/explore?limit=10")).toBe("/explore?limit=10")
    expect(safeExploreReturn("/explore/t/trace-a")).toBe("/explore/t/trace-a")
    expect(safeExploreReturn("https://evil.example")).toBe("/explore")
    expect(safeExploreReturn("//evil.example")).toBe("/explore")
    expect(safeExploreReturn("javascript:alert(1)")).toBe("/explore")
    expect(safeExploreReturn(undefined)).toBe("/explore")
  })
})
