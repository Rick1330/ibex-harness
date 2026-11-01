import { formatGovernDate, formatGovernStamp } from "@/lib/govern-format"

/**
 * Relative time for the two live surfaces (Overview and Platform).
 *
 * `formatGovernRelative` anchors ages to the recorded fixture clock so preview pages render
 * identically on server and client and a fixture never reads "3 minutes ago" next year. Live data
 * has no fixed clock, so it is measured against the caller's wall clock — passed in by the page,
 * which refreshes it on a timer. Nothing here reads `Date.now()` itself: that would let one
 * snapshot render two different ages in a single pass.
 *
 * Absolute stamps keep using the shared `formatGovernStamp`, so "27 Oct 2026, 03:00 UTC" is the
 * only written-out time format in the console, live or preview.
 */

export function liveAgeSeconds(value: string | null | undefined, nowMs: number | null): number | null {
  if (!value || nowMs === null) return null
  const timestamp = Date.parse(value)
  if (Number.isNaN(timestamp)) return null
  return Math.max(0, Math.floor((nowMs - timestamp) / 1_000))
}

/** Relative for a cell, with `formatGovernStamp` kept for the hover and the tooltip. */
export function formatLiveRelative(value: string | null | undefined, nowMs: number | null): string {
  const seconds = liveAgeSeconds(value, nowMs)
  if (seconds === null) return "Age not measured"
  if (seconds < 10) return "just now"
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3_600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86_400) return `${Math.floor(seconds / 3_600)}h ago`
  if (seconds < 30 * 86_400) return `${Math.floor(seconds / 86_400)}d ago`
  return value ? formatGovernDate(value) : "Not recorded"
}

export type LiveStaleness = {
  ageSeconds: number | null
  stale: boolean
  /** Reads after a verb: "read 14h ago". */
  label: string
  /** Reads as a property of the thing itself: "snapshot is 14h old". */
  asSpan: string
}

/** Staleness measured from the reported observation time, never from request time. */
export function liveStaleness(
  observedAt: string | null | undefined,
  nowMs: number | null,
  boundSeconds: number,
): LiveStaleness {
  const ageSeconds = liveAgeSeconds(observedAt, nowMs)
  if (ageSeconds === null) {
    return { ageSeconds: null, stale: false, label: "Age not measured", asSpan: "Age not measured" }
  }
  const label = observedAt ? formatLiveRelative(observedAt, nowMs) : formatGovernStamp(null)
  return { ageSeconds, stale: ageSeconds > boundSeconds, label, asSpan: label.replace(/ ago$/, " old") }
}
