import { describe, expect, it } from "vitest"

import { getSessionPreview, getSessionThread } from "../app/lib/session-preview"
import {
  criticalSpanIds,
  driftState,
  formatCostShort,
  formatMs,
  parseClockMs,
  parseCostUsd,
  parseDurationMs,
  roundOffsetMs,
  sessionAgentTimeMs,
  sessionDriftCount,
  sessionPrivacy,
  sessionTotals,
  sessionWallTimeMs,
  spanShare,
  spanTotalMs,
  stepRows,
  totalToolCalls,
  traceEndMs,
  turnToolMs,
  unaccountedMs,
} from "../app/lib/session-detail"

const session = getSessionPreview("ses_2481f0a2")
const rounds = getSessionThread(session)
const first = rounds[0]!

describe("session detail derived values", () => {
  it("aggregates totals across every rendered turn", () => {
    const totals = sessionTotals(session, rounds)
    expect(totals.complete).toBe(true)
    expect(totals.tokensIn).toBe(2_966)
    expect(totals.tokensOut).toBe(441)
    expect(totals.tokensLabel).toBe("2,966 in · 441 out")
    expect(totals.costExact).toBe("$0.09021")
    expect(totals.costShort).toBe("$0.090")
  })

  it("keeps agent time and wall time as separate, labelled measurements", () => {
    expect(sessionAgentTimeMs(rounds)).toBe(1_180)
    expect(sessionWallTimeMs(session)).toBe(14_050)
    expect(formatMs(sessionAgentTimeMs(rounds))).toBe("1.18 s")
    expect(formatMs(sessionWallTimeMs(session))).toBe("14.05 s")
  })

  it("derives turn offsets from the first recorded message", () => {
    expect(rounds.map((round) => roundOffsetMs(session, round))).toEqual([0, 5_000, 9_000, 12_000])
  })

  it("counts the refund preview tool and its 60 ms of tool time", () => {
    expect(turnToolMs(first)).toBe(60)
    expect(first.toolCalls.some((tool) => tool.name === "refund.preview")).toBe(true)
    expect(stepRows(first).some((row) => row.label === "tool.refund.preview")).toBe(true)
    expect(totalToolCalls(rounds)).toBe(6)
  })

  it("keeps every span inside the trace scale and reports unaccounted time", () => {
    expect(traceEndMs(first)).toBe(320)
    expect(unaccountedMs(first)).toBe(0)
    expect(spanTotalMs(first)).toBe(338)
    for (const round of rounds) {
      expect(traceEndMs(round)).toBeLessThanOrEqual(round.latencyMs)
      expect(unaccountedMs(round)).toBeGreaterThanOrEqual(0)
    }
  })

  it("marks a critical span chain and a bounded share", () => {
    const critical = criticalSpanIds(first.spans)
    expect(critical.has("span-t1-provider")).toBe(true)
    const provider = first.spans.find((span) => span.id === "span-t1-provider")!
    expect(spanShare(provider, spanTotalMs(first))).toBe(49)
  })

  it("distinguishes advisory, clean, and not-checked drift states", () => {
    expect(rounds.map(driftState)).toEqual(["not_checked", "clean", "advisory", "advisory"])
    expect(sessionDriftCount(rounds)).toBe(2)
  })

  it("exposes per-turn capture and redaction state", () => {
    const redactedRound = getSessionThread(getSessionPreview("ses_18bd3e09"))[0]!
    const privacy = sessionPrivacy(redactedRound)
    expect(privacy.captureMode).toBe("redacted")
    expect(privacy.completeness).toBe("redacted")
    expect(privacy.redactionClass).toBe("redacted")
    expect(privacy.redactionProofVersion).toBe("session-metadata-allowlist/v1")
    expect(privacy.droppedFields).toContain("content")
    expect(privacy.pii.detected).toBe(true)
    expect(privacy.pii.findings.every((finding) => finding.score >= privacy.pii.threshold)).toBe(true)

    const clean = sessionPrivacy(rounds[0]!)
    expect(clean.captureMode).toBe("metadata")
    expect(clean.completeness).toBe("complete")
    expect(clean.pii.detected).toBe(false)
  })

  it("parses clocks, durations, and costs defensively", () => {
    expect(parseClockMs("13:09:29")).toBe(47_369_000)
    expect(parseDurationMs("14.05s")).toBe(14_050)
    expect(parseDurationMs("1m 15s")).toBe(75_000)
    expect(parseCostUsd("$0.09021")).toBeCloseTo(0.09021, 5)
    expect(formatCostShort(0.0004)).toBe("$0.00040")
  })
})
