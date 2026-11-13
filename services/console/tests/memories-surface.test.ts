import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("memories live contract", () => {
  it("is live with the metadata-only operator contract", () => {
    expect(SURFACES.memories.availability).toBe("live")
    expect(SURFACES.memories.contract).toBe("operator.memories.read.v1")
    expect(SURFACES.memories.contractStatus).toBe("registry")
  })

  it("does not claim content exposure", () => {
    expect(SURFACES.memories.description).not.toContain("planned")
    expect(SURFACES.memories.contractStatus).toBe("registry")
    expect(SURFACES.memories.description.toLowerCase()).not.toContain("content")
  })
})
