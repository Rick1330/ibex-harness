import { describe, expect, it } from "vitest"

import {
  activeSessionFilterCount,
  emptySessionListState,
  filterSessions,
  hasSessionFilters,
  parseDurationSeconds,
  parseSessionListQuery,
  serializeSessionListQuery,
  sessionListHref,
  sortSessions,
} from "../app/lib/session-list-query"
import { previewSessions } from "../app/lib/session-preview"

describe("session list query", () => {
  it("uses stable defaults for empty or invalid input", () => {
    expect(parseSessionListQuery({})).toEqual(emptySessionListState())

    const parsed = parseSessionListQuery({
      q: 42,
      view: "everything",
      env: ["production", "moon", "production"],
      outcome: "denied,sideways",
      tier: "T9",
      duration: "forever",
      hide: "coverage,turns,nope",
      sort: "unknown",
      dir: "sideways",
    })

    expect(parsed.search).toBe("")
    expect(parsed.view).toBe("all")
    expect(parsed.environments).toEqual(["production"])
    expect(parsed.outcomes).toEqual(["denied"])
    expect(parsed.tier).toBe("")
    expect(parsed.duration).toBe("")
    expect(parsed.hidden).toEqual(["coverage", "turns"])
    expect(parsed.sort).toBe("activity")
    expect(parsed.direction).toBe("desc")
  })

  it("parses and bounds shareable filter state", () => {
    const parsed = parseSessionListQuery({
      q: "  refund  ",
      view: "support",
      env: "staging,production",
      outcome: "denied,error",
      tier: "T1",
      agent: "Support triage",
      id: "ses_18",
      duration: "long",
      hide: "id,cost",
      sort: "cost",
      dir: "asc",
    })

    expect(parsed.search).toBe("refund")
    expect(parsed.view).toBe("support")
    expect(parsed.environments).toEqual(["staging", "production"])
    expect(parsed.outcomes).toEqual(["denied", "error"])
    expect(parsed.tier).toBe("T1")
    expect(parsed.agent).toBe("Support triage")
    expect(parsed.id).toBe("ses_18")
    expect(parsed.duration).toBe("long")
    expect(parsed.hidden).toEqual(["id", "cost"])
    expect(parsed.sort).toBe("cost")
    expect(parsed.direction).toBe("asc")
  })

  it("round-trips only non-default state into a shareable href", () => {
    const state = emptySessionListState()
    state.search = "refund"
    state.view = "security"
    state.environments = ["staging"]
    state.outcomes = ["denied"]
    state.duration = "short"
    state.hidden = ["coverage"]
    state.sort = "cost"
    state.direction = "asc"

    const query = serializeSessionListQuery(state)
    expect(query.get("q")).toBe("refund")
    expect(query.get("view")).toBe("security")
    expect(query.get("env")).toBe("staging")
    expect(query.get("outcome")).toBe("denied")
    expect(query.get("duration")).toBe("short")
    expect(query.get("hide")).toBe("coverage")
    expect(query.get("sort")).toBe("cost")
    expect(query.get("dir")).toBe("asc")
    expect(query.get("tier")).toBeNull()

    expect(sessionListHref(state)).toBe(
      "/sessions?q=refund&view=security&env=staging&outcome=denied&duration=short&hide=coverage&sort=cost&dir=asc",
    )
    expect(parseSessionListQuery(Object.fromEntries(query))).toEqual(state)
  })

  it("counts active filters without counting empty groups", () => {
    const state = emptySessionListState()
    expect(hasSessionFilters(state)).toBe(false)
    expect(activeSessionFilterCount(state)).toBe(0)

    state.view = "support"
    state.environments = ["production", "staging"]
    state.tier = "T2"
    state.duration = "short"
    expect(activeSessionFilterCount(state)).toBe(5)
    expect(hasSessionFilters(state)).toBe(true)

    state.search = "refund"
    expect(hasSessionFilters(state)).toBe(true)
  })

  it("filters by view, environment, outcome, identity, and duration", () => {
    expect(filterSessions(previewSessions, { ...emptySessionListState(), view: "security" })).toHaveLength(2)
    expect(
      filterSessions(previewSessions, { ...emptySessionListState(), environments: ["staging"] }).every(
        (session) => session.env === "staging",
      ),
    ).toBe(true)
    expect(
      filterSessions(previewSessions, { ...emptySessionListState(), outcomes: ["error"] }).every(
        (session) => session.outcome === "error",
      ),
    ).toBe(true)
    expect(filterSessions(previewSessions, { ...emptySessionListState(), id: "ses_18bd" })).toHaveLength(1)
    expect(
      filterSessions(previewSessions, { ...emptySessionListState(), duration: "long" }).every(
        (session) => parseDurationSeconds(session.duration) > 30,
      ),
    ).toBe(true)
    expect(filterSessions(previewSessions, { ...emptySessionListState(), search: "invoice export" })).toHaveLength(1)
  })

  it("sorts by activity, turns, duration, and cost in both directions", () => {
    const activity = sortSessions(previewSessions, "activity", "desc")
    expect(activity[0]?.id).toBe("ses_2481f0a2")
    expect(sortSessions(previewSessions, "activity", "asc")[0]?.id).toBe("ses_9c02a741")

    expect(sortSessions(previewSessions, "turns", "asc")[0]?.turns).toBe(2)
    expect(sortSessions(previewSessions, "turns", "desc")[0]?.turns).toBe(9)

    const durations = sortSessions(previewSessions, "duration", "asc").map((session) =>
      parseDurationSeconds(session.duration),
    )
    expect(durations).toEqual([...durations].sort((first, second) => first - second))

    const costs = sortSessions(previewSessions, "cost", "asc").map((session) =>
      Number.parseFloat(session.cost.replace(/[^0-9.]/g, "")),
    )
    expect(costs).toEqual([...costs].sort((first, second) => first - second))
  })
})
