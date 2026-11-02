import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("memories live contract", () => {
  it("is live with the metadata-only operator contract", () => {
    expect(SURFACES.memories.availability).toBe("live")
    expect(SURFACES.memories.contract).toBe("operator.memories.v1")
  })

  it("does not claim content exposure", () => {
    expect(SURFACES.memories.description).not.toContain("planned")
    expect(SURFACES.memories.contract).not.toContain("NEEDS-BACKEND")
    expect(SURFACES.memories.description.toLowerCase()).not.toContain("content")
  })
})
