import { describe, expect, it } from "vitest"

import { safeExploreReturn } from "../app/lib/return-to"

const SESSION = "77777777-7777-4777-8777-777777777777"
const MEMORY = "44444444-4444-4444-8444-444444444444"

describe("explore return target", () => {
  it("accepts only local explore paths", () => {
    expect(safeExploreReturn("/explore?limit=10")).toBe("/explore?limit=10")
    expect(safeExploreReturn("/explore/t/trace-a")).toBe("/explore/t/trace-a")
    expect(safeExploreReturn("https://evil.example")).toBe("/explore")
    expect(safeExploreReturn("//evil.example")).toBe("/explore")
    expect(safeExploreReturn("javascript:alert(1)")).toBe("/explore")
    expect(safeExploreReturn(undefined)).toBe("/explore")
  })

  it("accepts the record page a trace link came from", () => {
    // A session turn links to Explore with the session as its back target; a
    // memory provenance link does the same for the memory.
    expect(safeExploreReturn(`/sessions/${SESSION}`)).toBe(`/sessions/${SESSION}`)
    expect(safeExploreReturn(`/sessions/${SESSION}?return=%2Fsessions%3Fstatus%3Derror`)).toBe(
      `/sessions/${SESSION}?return=%2Fsessions%3Fstatus%3Derror`,
    )
    expect(safeExploreReturn(`/memories/${MEMORY}`)).toBe(`/memories/${MEMORY}`)
  })

  it("rejects record-shaped paths that are not a checked record id", () => {
    expect(safeExploreReturn("/sessions")).toBe("/explore")
    expect(safeExploreReturn("/sessions/not-a-uuid")).toBe("/explore")
    expect(safeExploreReturn(`/sessions/${SESSION}/../secrets`)).toBe("/explore")
    expect(safeExploreReturn(`/sessions/${SESSION}#frag`)).toBe("/explore")
    expect(safeExploreReturn(`//sessions/${SESSION}`)).toBe("/explore")
    expect(safeExploreReturn(`/admin/${SESSION}`)).toBe("/explore")
  })
})
