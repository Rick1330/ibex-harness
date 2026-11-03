import { describe, expect, it } from "vitest"

import { SURFACES } from "../shared/operator/surfaces"

describe("sessions live contract", () => {
  it("is live with the operator session contract", () => {
    expect(SURFACES.sessions.availability).toBe("live")
    expect(SURFACES.sessions.contract).toBe("operator.sessions.v1")
  })

  it("claims the turn-to-trace ledger, not content", () => {
    expect(SURFACES.sessions.description).not.toContain("planned")
    expect(SURFACES.sessions.description).toContain("turn-to-trace")
    expect(SURFACES.sessions.description.toLowerCase()).not.toContain("content")
  })
})
