import { describe, expect, it } from "vitest"

import { formatLiveRelative, liveAgeSeconds, liveStaleness } from "../app/lib/live-format"
import { PLATFORM_STALE_AFTER_SECONDS } from "../app/lib/platform-readiness"

const NOW = Date.parse("2026-10-30T15:12:00Z")

function stamp(secondsAgo: number): string {
  return new Date(NOW - secondsAgo * 1_000).toISOString()
}

describe("live relative time", () => {
  it("never reads the clock itself, so one render cannot show two ages", () => {
    expect(liveAgeSeconds(stamp(60), null)).toBeNull()
    expect(formatLiveRelative(stamp(60), null)).toBe("Age not measured")
    expect(formatLiveRelative(null, NOW)).toBe("Age not measured")
    expect(liveAgeSeconds("not-a-timestamp", NOW)).toBeNull()
  })

  it("clamps a future observation to zero rather than a negative age", () => {
    expect(liveAgeSeconds(stamp(-120), NOW)).toBe(0)
  })

  it("steps seconds, minutes, hours and days", () => {
    expect(formatLiveRelative(stamp(4), NOW)).toBe("just now")
    expect(formatLiveRelative(stamp(45), NOW)).toBe("45s ago")
    expect(formatLiveRelative(stamp(185), NOW)).toBe("3m ago")
    expect(formatLiveRelative(stamp(7_200), NOW)).toBe("2h ago")
    expect(formatLiveRelative(stamp(172_800), NOW)).toBe("2d ago")
  })

  it("falls back to the shared absolute date instead of an endless relative count", () => {
    expect(formatLiveRelative(stamp(40 * 86_400), NOW)).toBe("20 Sept 2026")
  })
})

describe("staleness bound", () => {
  it("uses the single recorded bound and stays honest without an observation time", () => {
    expect(PLATFORM_STALE_AFTER_SECONDS).toBe(300)
    const fresh = liveStaleness(stamp(120), NOW, PLATFORM_STALE_AFTER_SECONDS)
    expect(fresh).toEqual({ ageSeconds: 120, stale: false, label: "2m ago", asSpan: "2m old" })
    const old = liveStaleness(stamp(301), NOW, PLATFORM_STALE_AFTER_SECONDS)
    expect(old.stale).toBe(true)
    expect(liveStaleness(null, NOW, PLATFORM_STALE_AFTER_SECONDS)).toEqual({
      ageSeconds: null,
      stale: false,
      label: "Age not measured",
      asSpan: "Age not measured",
    })
  })
})
