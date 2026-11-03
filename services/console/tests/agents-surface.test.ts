import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("agents live contract", () => {
  it("is live once the operator read model is connected", () => {
    expect(SURFACES.agents.availability).toBe("live")
    expect(SURFACES.agents.contract).toBe("operator.agents.v1")
  })

  it("does not claim unimplemented health, budget, or drift fields", () => {
    expect(SURFACES.agents.description).not.toContain("planned")
    expect(SURFACES.agents.contract).not.toContain("NEEDS-BACKEND")
  })
})
