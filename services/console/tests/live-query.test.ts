import { describe, expect, it } from "vitest"

import {
  LiveExploreQueryError,
  liveExploreHref,
  parseLiveExploreQuery,
  serializeLiveExploreQuery,
} from "../src/lib/explore/live-query"

describe("live explore query codec", () => {
  it("round-trips allowlisted fields and drops cursor when requested", () => {
    const parsed = parseLiveExploreQuery(
      new URLSearchParams("limit=25&status=error&trace_id=trace-a&cursor=abc"),
    )
    expect(parsed.limit).toBe(25)
    expect(parsed.status).toBe("error")
    const serialized = serializeLiveExploreQuery(parsed)
    expect(serialized.get("cursor")).toBe("abc")
    expect(serializeLiveExploreQuery(parsed, { dropCursor: true }).get("cursor")).toBeNull()
    expect(liveExploreHref(parsed, { dropCursor: true })).toContain("status=error")
  })

  it("rejects unknown fields, oversized values, and invalid status", () => {
    expect(() => parseLiveExploreQuery(new URLSearchParams("foo=1"))).toThrow(LiveExploreQueryError)
    expect(() => parseLiveExploreQuery(new URLSearchParams("status=weird"))).toThrow(LiveExploreQueryError)
    expect(() => parseLiveExploreQuery(new URLSearchParams(`cursor=${"x".repeat(2049)}`))).toThrow(
      LiveExploreQueryError,
    )
  })
})
