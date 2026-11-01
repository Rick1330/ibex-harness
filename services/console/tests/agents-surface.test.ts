import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("agents preview contract", () => {
  it("remains preview-only until the agent summary API is connected", () => {
    expect(SURFACES.agents.availability).toBe("preview")
    expect(SURFACES.agents.contract).toContain("operator.agents.summary.v1")
  })

  it("does not expose an unverified live agents contract", () => {
    expect(SURFACES.agents.description).toContain("planned")
    expect(SURFACES.agents.contract).toContain("[NEEDS-BACKEND]")
  })
})
