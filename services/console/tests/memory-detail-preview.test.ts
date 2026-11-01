import { describe, expect, it } from "vitest"

import {
  MEMORY_DETAIL_TITLES,
  MEMORY_LIFECYCLE_KINDS,
  MEMORY_VERSION_OPERATIONS,
  getMemoryDetail,
  memorySafetyVerdict,
  memoryValidityWindow,
  type MemoryDetail,
} from "../app/lib/memory-detail-preview"
import { previewMemories } from "../app/lib/memory-preview"
import { previewSessions } from "../app/lib/session-preview"

function detailFor(id: string): MemoryDetail {
  const detail = getMemoryDetail(id)
  expect(detail, id).not.toBeNull()
  return detail!
}

describe("memory detail fixtures", () => {
  it("returns null for unknown or out-of-org IDs", () => {
    expect(getMemoryDetail("mem_does_not_exist")).toBeNull()
    expect(getMemoryDetail("")).toBeNull()
    expect(getMemoryDetail("../../etc/passwd")).toBeNull()
  })

  it("covers every list fixture with a title, history, and lifecycle event", () => {
    expect(Object.keys(MEMORY_DETAIL_TITLES).sort()).toEqual(previewMemories.map((memory) => memory.id).sort())

    for (const memory of previewMemories) {
      const detail = detailFor(memory.id)
      expect(detail.title.length).toBeGreaterThan(0)
      expect(detail.orgId).toBe("org_demo_42")
      expect(detail.versions.length).toBeGreaterThanOrEqual(1)
      expect(detail.lifecycleEvents.length).toBeGreaterThanOrEqual(1)
      expect(detail.versions.every((version) => MEMORY_VERSION_OPERATIONS.includes(version.operation))).toBe(true)
      expect(detail.lifecycleEvents.every((event) => MEMORY_LIFECYCLE_KINDS.includes(event.kind))).toBe(true)
      expect(detail.lifecycleRevision).toBeGreaterThanOrEqual(1)
      expect(detail.retrieval.sparkline).toHaveLength(14)
    }
  })

  it("returns the same cached record for repeated reads", () => {
    expect(getMemoryDetail("mem_77b031")).toBe(getMemoryDetail("mem_77b031"))
  })

  it("gates raw content for redacted, quarantined, and tombstoned memories", () => {
    const redacted = detailFor("mem_9e13c2ab")
    expect(redacted.rawContentGate).toBe("redacted")
    expect(redacted.rawContent).toBeNull()
    expect(redacted.versions.every((version) => version.previousContent === null && version.newContent === null)).toBe(true)

    const quarantined = detailFor("mem_9c02a741")
    expect(quarantined.rawContentGate).toBe("privileged")
    expect(quarantined.rawContent).toBeNull()

    const tombstoned = detailFor("mem_3f71d2aa")
    expect(tombstoned.tombstoned).toBe(true)
    expect(tombstoned.rawContentGate).toBe("tombstoned")
    expect(tombstoned.rawContent).toBeNull()
    expect(tombstoned.deletionReceipt).toContain("del_")
    expect(tombstoned.retrieval.count).toBe(0)
    expect(tombstoned.versions.every((version) => version.previousContent === null && version.newContent === null)).toBe(true)
  })

  it("keeps raw content available only for open gates", () => {
    const open = detailFor("mem_77b031")
    expect(open.rawContentGate).toBe("open")
    expect(open.rawContent).toBe(open.memory.content)
  })

  it("preserves typed outgoing and incoming lineage edges", () => {
    const policy = detailFor("mem_77b031")
    expect(policy.lineage.edges.some((edge) => edge.type === "supersedes" && edge.memoryId === "mem_4c81a2")).toBe(true)
    expect(policy.lineage.edges.some((edge) => edge.type === "specializes" && edge.memoryId === "mem_2ab90f31")).toBe(true)

    const conflict = detailFor("mem_d2f79fa2")
    expect(conflict.lineage.edges.some((edge) => edge.type === "contradicts" && edge.memoryId === "mem_7b30d4e8")).toBe(true)

    const merged = detailFor("mem_075ef6a2")
    expect(merged.lineage.edges.some((edge) => edge.type === "merged_from" && edge.memoryId === "mem_cf2f18b9")).toBe(true)
  })

  it("resolves the supersession chain to the active tip", () => {
    const superseded = detailFor("mem_4c81a2")
    const tip = superseded.lineage.chain.at(-1)
    expect(tip?.id).toBe("mem_77b031")
    expect(tip?.isTip).toBe(true)
    expect(tip?.status).toBe("active")
    expect(superseded.lineage.chain.some((step) => step.id === "mem_4c81a2" && step.isCurrent)).toBe(true)
  })

  it("exposes retrieval evidence only for known preview sessions", () => {
    const detail = detailFor("mem_77b031")
    expect(detail.retrieval.sessions.length).toBeGreaterThan(0)
    expect(detail.retrieval.sessions.every((session) => previewSessions.some((entry) => entry.id === session.id))).toBe(true)
    expect(detail.retrieval.scoreTerms.every((term) => term.weight > 0)).toBe(true)
    expect(detail.retrieval.avgComposite).toBeGreaterThan(0)
  })

  it("links retrieval sessions for every retrievable memory", () => {
    for (const memory of previewMemories) {
      if (memory.retrievalCount === 0) continue
      if (memory.status === "quarantined" || memory.status === "deleted") continue

      const detail = detailFor(memory.id)
      expect(detail.retrieval.sessions.length, memory.id).toBeGreaterThan(0)
      expect(detail.retrieval.sessions.length, memory.id).toBeLessThanOrEqual(Math.min(3, memory.retrievalCount))
      expect(detail.retrieval.sessions[0]?.usage, memory.id).toBe("injected")
    }
  })

  it("scores linked retrieval sessions and derives injection usage", () => {
    const detail = detailFor("mem_77b031")
    for (const session of detail.retrieval.sessions) {
      expect(session.score).toBeGreaterThan(0)
      expect(session.score).toBeLessThanOrEqual(1)
      if (session.usage === "injected") expect(session.score).toBeGreaterThanOrEqual(0.8)
      if (session.usage === "retrieved_only") expect(session.score).toBeGreaterThanOrEqual(0.6)
      if (session.usage === "below_threshold") expect(session.score).toBeLessThan(0.6)
    }
    expect(detail.retrieval.sessions.some((session) => session.usage === "injected")).toBe(true)
  })

  it("excludes quarantined and tombstoned records from retrieval evidence", () => {
    for (const id of ["mem_9c02a741", "mem_9e13c2ab", "mem_3f71d2aa"]) {
      const detail = detailFor(id)
      expect(detail.retrieval.sessions, id).toEqual([])
      expect(detail.retrieval.count, id).toBe(0)
    }
  })

  it("computes half-open validity windows from the fixed preview clock", () => {
    const open = memoryValidityWindow(detailFor("mem_77b031"))
    expect(open.state).toBe("open")
    expect(open.end).toBeNull()

    const expiring = memoryValidityWindow(detailFor("mem_6b6c5cf3"))
    expect(expiring.state).toBe("expired")
    expect(expiring.progress).toBe(100)
    expect(expiring.durationDays).toBeGreaterThan(0)
  })

  it("derives one safety verdict shared by the header, vitals, and safety panel", () => {
    expect(memorySafetyVerdict(detailFor("mem_77b031"))).toBe("clear")
    expect(memorySafetyVerdict(detailFor("mem_9c02a741"))).toBe("blocked")
    expect(memorySafetyVerdict(detailFor("mem_44e8a1b0"))).toBe("review")
  })

  it("records applicability only where the fixture can support it", () => {
    const preference = detailFor("mem_6f9a71c4")
    expect(preference.appliesTo).toEqual(["Refund status updates"])
    expect(preference.subject).toBeNull()

    for (const memory of previewMemories) {
      const detail = detailFor(memory.id)
      expect(Array.isArray(detail.appliesTo), memory.id).toBe(true)
      expect(detail.appliesTo.every((scope) => scope.trim().length > 0), memory.id).toBe(true)
      expect(detail.subject === null || detail.subject.trim().length > 0, memory.id).toBe(true)
    }
  })

  it("does not present an undefined confidence as calibrated confidence", () => {
    for (const memory of previewMemories) {
      const detail = detailFor(memory.id)
      expect(detail.confidenceMeaning.value, memory.id).toBe(memory.confidence)
      expect(detail.confidenceMeaning.definition, memory.id).toBeNull()
      expect(detail.confidenceMeaning.basis, memory.id).toBeNull()
    }
  })

  it("exposes PII findings only when detection is recorded", () => {
    const redacted = detailFor("mem_9e13c2ab")
    expect(redacted.pii.detected).toBe(true)
    expect(redacted.pii.redacted).toBe(true)
    expect(redacted.pii.threshold).toBeGreaterThan(0)
    expect(redacted.pii.findings.length).toBeGreaterThan(0)
    expect(redacted.pii.findings.every((finding) => finding.score >= redacted.pii.threshold)).toBe(true)
    expect(redacted.pii.findings.every((finding) => finding.action === "redacted")).toBe(true)

    const clean = detailFor("mem_77b031")
    expect(clean.pii.detected).toBe(false)
    expect(clean.pii.findings).toEqual([])
  })

  it("separates completed checks from findings and unevaluated checks", () => {
    for (const memory of previewMemories) {
      const detail = detailFor(memory.id)
      const ids = detail.evaluation.checks.map((check) => check.id)
      expect(ids, memory.id).toEqual(["pii", "injection", "embedding"])
      expect(
        detail.evaluation.checks.every((check) => ["no_finding", "finding", "not_evaluated"].includes(check.result)),
        memory.id,
      ).toBe(true)
      expect(detail.evaluation.note, memory.id).not.toContain("certified")
    }

    const quarantined = detailFor("mem_9c02a741")
    expect(quarantined.evaluation.checks.find((check) => check.id === "injection")?.result).toBe("finding")
    expect(detailFor("mem_6f9a71c4").evaluation.checks.every((check) => check.result === "no_finding")).toBe(true)
  })
})
