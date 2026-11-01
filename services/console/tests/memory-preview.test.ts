import { describe, expect, it } from "vitest"

import {
  MEMORY_CATEGORIES,
  MEMORY_STATUSES,
  emptyMemoryFilters,
  memoryConfidenceBand,
  memoryInjectionBand,
  memoryRelativeTime,
  memoryValidity,
  previewMemories,
} from "../app/lib/memory-preview"

describe("memory preview helpers", () => {
  it("derives validity windows from the fixed preview clock", () => {
    expect(memoryValidity(null)).toEqual({ state: "open", label: "open" })
    expect(memoryValidity("2027-01-31T23:59:59Z").state).toBe("open")
    expect(memoryValidity("2026-10-29T23:59:59Z")).toEqual({ state: "expiring", label: "3d left" })
    expect(memoryValidity("2026-10-21T23:59:59Z")).toEqual({ state: "expired", label: "5d expired" })
  })

  it("formats relative retrieval times without inventing observations", () => {
    expect(memoryRelativeTime(null)).toBe("never")
    expect(memoryRelativeTime("2026-10-27T14:09:00Z")).toBe("1m ago")
    expect(memoryRelativeTime("2026-10-27T13:10:00Z")).toBe("1h ago")
    expect(memoryRelativeTime("2026-10-20T10:00:00Z")).toBe("Oct 20")
  })

  it("classifies confidence and injection risk deterministically", () => {
    expect(memoryConfidenceBand(0.9)).toBe("high")
    expect(memoryConfidenceBand(0.75)).toBe("medium")
    expect(memoryConfidenceBand(0.749)).toBe("low")
    expect(memoryInjectionBand(0)).toBe("none")
    expect(memoryInjectionBand(0.1)).toBe("low")
    expect(memoryInjectionBand(0.5)).toBe("medium")
    expect(memoryInjectionBand(0.8)).toBe("high")
  })

  it("returns independent empty filter state", () => {
    const first = emptyMemoryFilters()
    const second = emptyMemoryFilters()
    first.categories.push("factual")
    expect(second.categories).toEqual([])
  })
})

describe("memory preview fixtures", () => {
  it("keeps 26 unique, schema-valid illustrative memories", () => {
    expect(previewMemories).toHaveLength(26)
    expect(new Set(previewMemories.map((memory) => memory.id)).size).toBe(26)

    for (const memory of previewMemories) {
      expect(memory.id).toMatch(/^mem_[a-z0-9]+$/)
      expect(MEMORY_CATEGORIES).toContain(memory.category)
      expect(MEMORY_STATUSES).toContain(memory.status)
      expect(memory.labels.length).toBeGreaterThanOrEqual(1)
      expect(memory.labels.length).toBeLessThanOrEqual(3)
      expect(memory.confidence).toBeGreaterThanOrEqual(0)
      expect(memory.confidence).toBeLessThanOrEqual(1)
      expect(memory.usefulness).toBeGreaterThanOrEqual(0)
      expect(memory.usefulness).toBeLessThanOrEqual(1)
      expect(memory.injectionRisk).toBeGreaterThanOrEqual(0)
      expect(memory.injectionRisk).toBeLessThanOrEqual(1)
      expect(memory.contentTokens).toBeGreaterThan(0)
      expect(memory.halfLifeDays).toBeGreaterThan(0)
      if (memory.status === "quarantined") expect(memory.quarantineReason).toBeTruthy()
    }
  })

  it("keeps multi-label rows ordered by their primary confidence", () => {
    for (const memory of previewMemories) {
      const primary = memory.labels.find((label) => label.label === memory.category)
      expect(primary, memory.id).toBeTruthy()
      expect(primary?.confidence, memory.id).toBe(memory.confidence)
      expect(Math.max(...memory.labels.map((label) => label.confidence))).toBe(memory.confidence)
    }
  })
})
