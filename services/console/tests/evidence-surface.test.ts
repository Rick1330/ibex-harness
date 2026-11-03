import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("evidence live contract", () => {
  it("is live with the summary contract", () => {
    expect(SURFACES.evidence.availability).toBe("live")
    expect(SURFACES.evidence.contract).toBe("operator.evidence.summary.v1")
  })

  it("does not claim the parts the contract cannot prove", () => {
    const surface = SURFACES.evidence
    expect(surface.contract).not.toContain("NEEDS-BACKEND")
    expect(surface.description).not.toContain("planned")
    // The page reports capture completeness and delivery; a "certified" claim
    // would need a per-run digest the schema does not hold.
    expect(surface.question.toLowerCase()).not.toContain("certified")
    expect(surface.description.toLowerCase()).not.toContain("certified")
  })
})
