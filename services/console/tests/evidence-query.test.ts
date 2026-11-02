import { describe, expect, it } from "vitest"

import {
  defaultLiveEvidenceQuery,
  LiveEvidenceQueryError,
  parseLiveEvidenceQuery,
  parseLiveEvidenceQueryLenient,
  serializeLiveEvidenceQuery,
} from "../shared/operator/evidence-query"

describe("live evidence query codec", () => {
  it("defaults to the 24h coverage view", () => {
    expect(parseLiveEvidenceQuery(new URLSearchParams())).toEqual(defaultLiveEvidenceQuery())
    expect(defaultLiveEvidenceQuery()).toEqual({ tab: "coverage", range: "24h" })
  })

  it("round-trips every range and tab", () => {
    for (const range of ["24h", "7d", "30d"] as const) {
      for (const tab of ["coverage", "delivery", "tombstones", "redaction"] as const) {
        const value = { tab, range }
        expect(parseLiveEvidenceQuery(serializeLiveEvidenceQuery(value))).toEqual(value)
      }
    }
  })

  it("omits the default tab from the URL", () => {
    expect(serializeLiveEvidenceQuery({ tab: "coverage", range: "7d" }).toString()).toBe("range=7d")
  })

  it("rejects unknown fields and an unknown range", () => {
    expect(() => parseLiveEvidenceQuery({ view: "grid" })).toThrow(LiveEvidenceQueryError)
    expect(() => parseLiveEvidenceQuery({ range: "90d" })).toThrow(LiveEvidenceQueryError)
    expect(() => parseLiveEvidenceQuery({ tab: "chain" })).toThrow(LiveEvidenceQueryError)
  })

  it("keeps the fields that parse and drops the rest", () => {
    // A stale link must not silently reinterpret the window: the valid range
    // survives, the unknown tab and range fall back, and the page rewrites the
    // address bar to match what it reads.
    expect(parseLiveEvidenceQueryLenient({ tab: "chain", range: "7d" })).toEqual({
      tab: "coverage",
      range: "7d",
    })
    expect(parseLiveEvidenceQueryLenient({ range: "90d", extra: "1" })).toEqual(
      defaultLiveEvidenceQuery(),
    )
  })
})
