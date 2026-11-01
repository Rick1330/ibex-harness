import { describe, expect, it } from "vitest"

import {
  emptyMemoryListState,
  memoryDetailHref,
  memoryListHref,
  parseMemoryListQuery,
  serializeMemoryListQuery,
} from "../app/lib/memory-list-query"
import { safeMemoryReturn } from "../app/lib/return-to"

describe("memory list query", () => {
  it("uses stable defaults for empty or invalid input", () => {
    expect(parseMemoryListQuery({})).toEqual(emptyMemoryListState())

    const parsed = parseMemoryListQuery({
      q: 42,
      view: "unknown",
      status: ["active", "deleted", "not-a-status"],
      sort: "nope",
      dir: "sideways",
    })
    expect(parsed.search).toBe("")
    expect(parsed.view).toBe("all")
    expect(parsed.filters.statuses).toEqual(["active", "deleted"])
    expect(parsed.sort).toBe("updated")
    expect(parsed.direction).toBe("desc")
  })

  it("parses, deduplicates, and bounds comma-separated filters", () => {
    const parsed = parseMemoryListQuery({
      q: "  refund  ",
      view: "conflicts",
      category: "factual,procedural,factual",
      status: "active,quarantined",
      visibility: "org,agent",
      source: "extracted,user_provided",
      agent: "Support Triage",
      confidence: "high",
      safety: "pii,injection,conflict",
      validity: "expiring",
      sort: "retrievals",
      dir: "asc",
      tag: "refund,policy,refund",
      retrieved: "7d",
      group: "agent",
      density: "compact",
      cols: "source,validity,source,nope",
      tags: "0",
    })

    expect(parsed.search).toBe("refund")
    expect(parsed.view).toBe("conflicts")
    expect(parsed.filters.categories).toEqual(["factual", "procedural"])
    expect(parsed.filters.statuses).toEqual(["active", "quarantined"])
    expect(parsed.filters.visibilities).toEqual(["org", "agent"])
    expect(parsed.filters.sources).toEqual(["extracted", "user_provided"])
    expect(parsed.filters.agent).toBe("Support Triage")
    expect(parsed.filters.confidence).toBe("high")
    expect(parsed.filters.safety).toEqual(["pii", "injection", "conflict"])
    expect(parsed.filters.validity).toBe("expiring")
    expect(parsed.sort).toBe("retrievals")
    expect(parsed.direction).toBe("asc")
    expect(parsed.filters.tags).toEqual(["refund", "policy"])
    expect(parsed.filters.retrieval).toBe("7d")
    expect(parsed.group).toBe("agent")
    expect(parsed.density).toBe("compact")
    expect(parsed.columns).toEqual(["source", "validity"])
    expect(parsed.showTags).toBe(false)
  })

  it("round-trips only non-default state into a shareable href", () => {
    const state = emptyMemoryListState()
    state.search = "refund"
    state.view = "review"
    state.filters.statuses = ["quarantined"]
    state.sort = "confidence"
    state.direction = "asc"
    state.group = "lifecycle"
    state.density = "compact"
    state.columns = ["source", "lineage"]
    state.filters.tags = ["refund"]
    state.filters.retrieval = "never"

    const query = serializeMemoryListQuery(state)
    expect(query.get("q")).toBe("refund")
    expect(query.get("view")).toBe("review")
    expect(query.get("status")).toBe("quarantined")
    expect(query.get("sort")).toBe("confidence")
    expect(query.get("dir")).toBe("asc")
    expect(query.get("group")).toBe("lifecycle")
    expect(query.get("density")).toBe("compact")
    expect(query.get("cols")).toBe("source,lineage")
    expect(query.get("tag")).toBe("refund")
    expect(query.get("retrieved")).toBe("never")
    expect(query.get("category")).toBeNull()

    const href = memoryListHref(state)
    expect(href).toBe(
      "/memories?q=refund&view=review&status=quarantined&tag=refund&retrieved=never&sort=confidence&dir=asc&group=lifecycle&density=compact&cols=source%2Clineage",
    )
    expect(parseMemoryListQuery(Object.fromEntries(query))).toEqual(state)
  })

  it("encodes detail IDs and the return path", () => {
    const href = memoryDetailHref("mem_77b031", "/memories?view=review&status=quarantined")
    expect(href).toBe("/memories/mem_77b031?return=%2Fmemories%3Fview%3Dreview%26status%3Dquarantined")
    expect(href).not.toContain("/memories//")
  })
})

describe("safe memory return", () => {
  it("allows list and session returns", () => {
    expect(safeMemoryReturn("/memories")).toBe("/memories")
    expect(safeMemoryReturn("/memories?view=review&agent=Support%20Triage")).toBe("/memories?view=review&agent=Support%20Triage")
    expect(safeMemoryReturn("/sessions/ses_2481f0a2")).toBe("/sessions/ses_2481f0a2")
  })

  it("fails closed for external, nested, and malformed returns", () => {
    expect(safeMemoryReturn(undefined)).toBe("/memories")
    expect(safeMemoryReturn("//evil.example")).toBe("/memories")
    expect(safeMemoryReturn("https://evil.example/memories")).toBe("/memories")
    expect(safeMemoryReturn("/explore")).toBe("/memories")
    expect(safeMemoryReturn("/memories/mem_77b031")).toBe("/memories")
  })
})
