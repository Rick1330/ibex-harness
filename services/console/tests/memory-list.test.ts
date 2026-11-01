import { describe, expect, it } from "vitest"

import { previewMemories } from "../app/lib/memory-preview"
import { emptyMemoryListState } from "../app/lib/memory-list-query"
import {
  activeMemoryFilterChips,
  activeMemoryFilterCount,
  filterMemories,
  groupMemories,
  hasActiveMemoryFilters,
  memoryAgentIndex,
  memoryFlags,
  memoryLifecycleCounts,
  memoryNeedsReview,
  memoryRetrievalSummary,
  memorySeverity,
  memoryViewIsModified,
  sortMemories,
  viewMatchesMemory,
} from "../app/lib/memory-list"

function stateWith(patch: Partial<ReturnType<typeof emptyMemoryListState>>) {
  return { ...emptyMemoryListState(), ...patch }
}

describe("memory list filtering", () => {
  it("derives saved-view membership from stored fields only", () => {
    expect(previewMemories).toHaveLength(26)
    expect(previewMemories.filter((memory) => viewMatchesMemory("review", memory))).toHaveLength(4)
    expect(previewMemories.filter((memory) => viewMatchesMemory("conflicts", memory))).toHaveLength(2)
    expect(previewMemories.filter((memory) => viewMatchesMemory("pinned", memory))).toHaveLength(5)
    expect(previewMemories.filter((memory) => viewMatchesMemory("never", memory))).toHaveLength(6)
    expect(previewMemories.filter((memory) => viewMatchesMemory("expiring", memory))).toHaveLength(4)
    expect(previewMemories.filter((memory) => viewMatchesMemory("tombstoned", memory))).toHaveLength(1)
  })

  it("combines view, search, tags, and retrieval filters without inventing rows", () => {
    const byView = filterMemories(previewMemories, stateWith({ view: "conflicts" }))
    expect(byView).toHaveLength(2)
    expect(byView.every((memory) => memory.conflict?.state === "open")).toBe(true)

    const bySearch = filterMemories(previewMemories, stateWith({ search: "europe/berlin" }))
    expect(bySearch.map((memory) => memory.id)).toEqual(["mem_d2f79fa2"])

    const byTag = filterMemories(previewMemories, stateWith({ filters: { ...emptyMemoryListState().filters, tags: ["refund"] } }))
    expect(byTag.length).toBeGreaterThan(0)
    expect(byTag.every((memory) => memory.tags.includes("refund"))).toBe(true)

    const never = filterMemories(
      previewMemories,
      stateWith({ filters: { ...emptyMemoryListState().filters, retrieval: "never" } }),
    )
    expect(never.every((memory) => memory.retrievalCount === 0)).toBe(true)
    expect(never).toHaveLength(6)
  })

  it("treats missing safety findings as unknown, not safe", () => {
    const pii = filterMemories(
      previewMemories,
      stateWith({ filters: { ...emptyMemoryListState().filters, safety: ["pii"] } }),
    )
    expect(pii.every((memory) => memory.piiDetected)).toBe(true)
    const unflagged = previewMemories.filter((memory) => !memory.piiDetected)
    expect(unflagged.length).toBeGreaterThan(0)
    expect(memoryFlags(unflagged[0]!).some((flag) => flag.kind === "pii")).toBe(false)
  })
})

describe("memory list sorting and grouping", () => {
  it("sorts deterministically with a stable id tiebreak", () => {
    const descending = sortMemories(previewMemories, "updated", "desc")
    const ascending = [...descending].reverse()
    expect(descending[0]!.updatedAt >= descending[1]!.updatedAt).toBe(true)
    expect(sortMemories(ascending, "updated", "asc").map((memory) => memory.id)).toEqual(
      [...previewMemories].sort((first, second) => {
        const result = Date.parse(first.updatedAt) - Date.parse(second.updatedAt)
        return result !== 0 ? result : first.id.localeCompare(second.id)
      }).map((memory) => memory.id),
    )
  })

  it("groups every row exactly once", () => {
    for (const key of ["agent", "category", "lifecycle", "scope"] as const) {
      const groups = groupMemories(previewMemories, key)
      expect(groups.length).toBeGreaterThan(0)
      expect(groups.reduce((total, group) => total + group.rows.length, 0)).toBe(previewMemories.length)
    }
    expect(groupMemories(previewMemories, "none")).toHaveLength(1)
  })
})

describe("memory list flags and counts", () => {
  it("marks exceptions without treating clean rows as certifications", () => {
    const quarantined = previewMemories.find((memory) => memory.status === "quarantined" && memory.injectionRisk < 0.8)!
    expect(memorySeverity(quarantined)).toBe("warning")
    expect(memoryFlags(quarantined).some((flag) => flag.kind === "pii" || flag.kind === "injection")).toBe(true)

    const clean = previewMemories.find(
      (memory) =>
        memory.status === "active" &&
        memory.injectionRisk === 0 &&
        !memory.piiDetected &&
        !memory.conflict &&
        memory.validity === "open",
    )!
    expect(memoryFlags(clean)).toEqual([])
    expect(memoryNeedsReview(clean)).toBe(false)
  })

  it("counts lifecycle statuses from the dataset", () => {
    expect(memoryLifecycleCounts(previewMemories)).toEqual([
      { status: "active", count: 20 },
      { status: "superseded", count: 1 },
      { status: "merged_into", count: 1 },
      { status: "archived", count: 1 },
      { status: "quarantined", count: 2 },
      { status: "deleted", count: 1 },
    ])
  })

  it("summarizes retrieval without claiming influence", () => {
    const never = previewMemories.find((memory) => memory.retrievalCount === 0)!
    expect(memoryRetrievalSummary(never)).toBe("Never retrieved")
    const used = previewMemories.find((memory) => memory.retrievalCount > 0)!
    expect(memoryRetrievalSummary(used)).toContain("retrievals")
  })

  it("derives deterministic agent tokens", () => {
    const ids = [...new Set(previewMemories.map((memory) => memory.agentId))]
    const first = ids.map(memoryAgentIndex)
    expect(first).toEqual(ids.map(memoryAgentIndex))
    expect(first.every((index) => index >= 1 && index <= 8)).toBe(true)
  })
})

describe("memory list filter chips", () => {
  it("round-trips chip removals through the filter state", () => {
    const state = stateWith({
      filters: {
        ...emptyMemoryListState().filters,
        statuses: ["quarantined"],
        safety: ["pii"],
        tags: ["refund"],
      },
    })
    expect(activeMemoryFilterCount(state)).toBe(3)
    expect(hasActiveMemoryFilters(state)).toBe(true)

    const chips = activeMemoryFilterChips(state)
    expect(chips.map((chip) => chip.field)).toEqual(["Lifecycle", "Flag", "Tag"])

    const withoutPii = chips.find((chip) => chip.field === "Flag")!
    expect(withoutPii.next.safety).toEqual([])
    expect(withoutPii.next.statuses).toEqual(["quarantined"])
    expect(withoutPii.next.tags).toEqual(["refund"])
  })

  it("flags a saved view as modified only when search or filters narrow it", () => {
    expect(memoryViewIsModified(emptyMemoryListState())).toBe(false)
    expect(memoryViewIsModified(stateWith({ search: "refund" }))).toBe(true)
  })
})
