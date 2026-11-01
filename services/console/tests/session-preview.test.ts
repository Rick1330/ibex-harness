import { describe, expect, it } from "vitest"

import { getSessionPreview, getSessionThread, previewSessions } from "../app/lib/session-preview"
import type { SessionRound } from "../app/lib/session-preview"

const threads = previewSessions.map((session) => ({ session, rounds: getSessionThread(session) }))

function allRounds(): SessionRound[] {
  return threads.flatMap(({ rounds }) => rounds)
}

describe("session preview evidence", () => {
  it("keeps every thread internally consistent", () => {
    for (const { session, rounds } of threads) {
      expect(rounds.length, session.id).toBeGreaterThan(0)
      expect(rounds.length, session.id).toBeLessThanOrEqual(session.turns)
      expect(rounds.map((round) => round.index)).toEqual(rounds.map((_, index) => index + 1))
      expect(new Set(rounds.map((round) => round.id)).size, session.id).toBe(rounds.length)
    }
  })

  it("keeps span timing inside the response and the waterfall scale", () => {
    for (const round of allRounds()) {
      expect(round.spans.length, round.traceId).toBeGreaterThan(0)
      expect(new Set(round.spans.map((span) => span.label)).size, round.traceId).toBe(round.spans.length)
      expect(round.spans.some((span) => span.kind === "llm"), round.traceId).toBe(true)

      for (const span of round.spans) {
        expect(span.offsetMs, `${round.traceId} ${span.label}`).toBeGreaterThanOrEqual(0)
        expect(span.durationMs, `${round.traceId} ${span.label}`).toBeGreaterThan(0)
        expect(span.offsetMs + span.durationMs, `${round.traceId} ${span.label}`).toBeLessThanOrEqual(round.latencyMs)
      }
    }
  })

  it("labels memory influence with bounded retrieval similarity", () => {
    for (const round of allRounds()) {
      for (const memory of round.memories) {
        expect(memory.similarity, memory.id).toBeGreaterThanOrEqual(0)
        expect(memory.similarity, memory.id).toBeLessThanOrEqual(1)
        expect(typeof memory.usedInResponse, memory.id).toBe("boolean")
        expect(memory.fact.length, memory.id).toBeGreaterThan(0)
        expect(memory.why.length, memory.id).toBeGreaterThan(0)
      }
    }
  })

  it("never presents an allowed decision beside a failed policy check", () => {
    for (const round of allRounds()) {
      expect(round.policy.checks.length, round.traceId).toBeGreaterThan(0)
      expect(round.policy.budgetDetail.length, round.traceId).toBeGreaterThan(0)
      expect(round.policy.rule.length, round.traceId).toBeGreaterThan(0)

      if (round.policy.decision === "allow") {
        expect(round.policy.checks.some((check) => check.result === "fail"), round.traceId).toBe(false)
      }
    }
  })

  it("describes directives and drift with grounded, non-empty evidence", () => {
    for (const round of allRounds()) {
      expect(round.directive.name.length).toBeGreaterThan(0)
      expect(round.directive.version).toMatch(/^v\d+$/)
      expect(round.directive.excerpt.length).toBeGreaterThan(0)
      expect(round.directive.previousVersion.length).toBeGreaterThan(0)

      if (round.drift) {
        expect(round.drift.uncertainty.length, round.drift.id).toBeGreaterThan(0)
        expect(round.drift.signal.length, round.drift.id).toBeGreaterThan(0)
        expect(["advisory", "warning", "critical"]).toContain(round.drift.severity)
      }
    }
  })

  it("falls back to the first illustrative session for unknown ids", () => {
    expect(getSessionPreview("ses_does_not_exist")).toBe(previewSessions[0])
  })
})
