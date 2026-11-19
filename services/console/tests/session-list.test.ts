import { describe, expect, it } from "vitest"

import {
  AGENT_ID_FILTER_INVALID,
  DEFAULT_SESSION_COLUMNS,
  DEFAULT_SESSION_PAGE_FILTERS,
  SESSION_STATUS_ORDER,
  agentFilterOptions,
  filterSessionRows,
  formatSessionLatency,
  matchesSessionSearch,
  parseAgentIdFilter,
  segmentSessionRows,
  sessionColumnVisible,
  sessionExtraction,
  sessionFacets,
  sessionPageFilterCount,
  activeSessionFilterCount,
  agentSecondaryLabel,
  sessionSegments,
  shortId,
  toSessionListRows,
  toggleSessionColumn,
  type SessionListRow,
  type SessionPageFilters,
} from "../app/lib/session-list"
import {
  OperatorAgentSchema,
  OperatorSessionRecordSchema,
  type OperatorAgent,
  type OperatorSessionRecord,
} from "../shared/operator/contracts"

const AGENT = "33333333-3333-4333-8333-333333333333"
const MISSING_AGENT = "99999999-9999-4999-8999-999999999999"
const SESSION = "77777777-7777-4777-8777-777777777777"

function session(overrides: Partial<OperatorSessionRecord> = {}): OperatorSessionRecord {
  return OperatorSessionRecordSchema.parse({
    id: SESSION,
    agent_id: AGENT,
    external_id: "ext-1",
    status: "active",
    model: "gpt-4.1",
    provider: "openai",
    directive_version_id: null,
    turn_count: 1,
    total_input_tokens: 10,
    total_output_tokens: 20,
    total_latency_ms: 100,
    last_extracted_turn: 0,
    lifecycle_revision: 1,
    evidence_fence_version: 1,
    created_at: "2026-11-02T12:00:00.000Z",
    updated_at: "2026-11-02T12:00:01.000Z",
    completed_at: null,
    ...overrides,
  })
}

function agent(overrides: Partial<OperatorAgent> = {}): OperatorAgent {
  return OperatorAgentSchema.parse({
    id: AGENT,
    slug: "support-agent",
    name: "Support Agent",
    description: null,
    status: "active",
    default_provider: "openai",
    default_model: "gpt-4.1",
    tags: ["prod"],
    total_sessions: 1,
    total_memories: 2,
    total_tokens_used: 3,
    last_active_at: null,
    created_at: "2026-09-26T12:00:00.000Z",
    updated_at: "2026-09-26T12:00:00.000Z",
    ...overrides,
  })
}

function row(overrides: Partial<OperatorSessionRecord> = {}, agents: OperatorAgent[] = [agent()]): SessionListRow {
  return toSessionListRows([session(overrides)], agents)[0] as SessionListRow
}

function rows(...sessions: OperatorSessionRecord[]): SessionListRow[] {
  return toSessionListRows(sessions, [agent()])
}

function filters(overrides: Partial<SessionPageFilters> = {}): SessionPageFilters {
  return { ...DEFAULT_SESSION_PAGE_FILTERS, ...overrides }
}

describe("session row identity", () => {
  it("shortens a uuid without touching a short value", () => {
    expect(shortId(SESSION)).toBe("77777777…7777")
    expect(shortId("sess-1")).toBe("sess-1")
  })

  it("joins the agent name and slug from the agents read", () => {
    const joined = row()
    expect(joined.agentName).toBe("Support Agent")
    expect(joined.agentSlug).toBe("support-agent")
    expect(joined.agentId).toBe(AGENT)
  })

  it("keeps the session's own agent id when the agent is not in the read", () => {
    const joined = row({ agent_id: MISSING_AGENT }, [])
    expect(joined.agentName).toBeNull()
    expect(joined.agentSlug).toBeNull()
    expect(joined.agentId).toBe(MISSING_AGENT)
  })

  it("never invents a name for an agent the read does not carry", () => {
    const joined = row({ agent_id: MISSING_AGENT })
    expect(joined.agentName).toBeNull()
    expect(joined.agentId).toBe(MISSING_AGENT)
  })

  it("explains a missing agent name without inventing one", () => {
    const missing = row({ agent_id: MISSING_AGENT }, [])
    expect(agentSecondaryLabel(missing, false)).toBe("Name not in this agent page")
    expect(agentSecondaryLabel(missing, true)).toBe("Agent read unavailable")
    expect(agentSecondaryLabel(row(), true)).toBe("support-agent")
  })

  it("carries the external id and the model on the identity line", () => {
    expect(row().meta).toBe("ext-1 · gpt-4.1")
    expect(row({ external_id: null }).meta).toBe("gpt-4.1")
  })
})

describe("session extraction", () => {
  it("reports a fully extracted four-turn session as its zero-based pointer, not as 4 of 4", () => {
    // `last_extracted_turn` points at the last extracted turn, whose index is 3.
    // The old percentage read this as 3/4 = 75% for a session with nothing left
    // to extract.
    const fullyExtracted = row({ turn_count: 4, last_extracted_turn: 3 })
    expect(fullyExtracted.extractionIndex).toBe(3)
    expect(fullyExtracted.extractionLabel).toBe("turn 3")
    expect(fullyExtracted.extractionNote).toBe("0-based index")
  })

  it("reports a one-turn session as turn 0, which is also the column default", () => {
    // 0 is both "the first turn was extracted" and "nothing has been extracted",
    // and the contract cannot tell them apart. Neither reads as a ratio.
    const oneTurn = row({ turn_count: 1, last_extracted_turn: 0 })
    expect(oneTurn.extractionIndex).toBe(0)
    expect(oneTurn.extractionLabel).toBe("turn 0")

    expect(sessionExtraction(0, 1)).toEqual({ index: 0, label: "turn 0", note: "0-based index" })
  })

  it("does not derive a count, a ratio or a percentage from the pointer", () => {
    // The view model has no percentage field at all: the pointer cannot support
    // one, so there is nothing to round.
    expect(Object.keys(sessionExtraction(2, 5)).sort()).toEqual(["index", "label", "note"])
    const covered = row({ turn_count: 5, last_extracted_turn: 2 })
    expect(covered).not.toHaveProperty("coveragePercent")
    expect(covered.extractionLabel).toBe("turn 2")
  })

  it("says nothing was recorded when the session has no turns to point at", () => {
    expect(sessionExtraction(0, 0)).toEqual({
      index: null,
      label: "Not recorded",
      note: "No turns recorded",
    })
  })
})

describe("session latency", () => {
  it("steps milliseconds, seconds and minutes", () => {
    expect(formatSessionLatency(100)).toBe("100 ms")
    expect(formatSessionLatency(4_200)).toBe("4.2 s")
    expect(formatSessionLatency(125_000)).toBe("2m 05s")
  })

  it("never prints a negative or unusable value", () => {
    expect(formatSessionLatency(-1)).toBe("Not recorded")
    expect(formatSessionLatency(Number.NaN)).toBe("Not recorded")
  })
})

describe("session activity", () => {
  it("uses the completion time while nothing advanced the record afterwards", () => {
    const completed = row({
      status: "completed",
      completed_at: "2026-11-02T13:00:00.000Z",
      updated_at: "2026-11-02T13:00:00.000Z",
    })
    expect(completed.activityKind).toBe("Completed")
    expect(completed.activityAt).toBe("2026-11-02T13:00:00.000Z")
  })

  it("uses the later update time when extraction advanced the record after completion", () => {
    const extractedLater = row({
      status: "completed",
      completed_at: "2026-11-02T13:00:00.000Z",
      updated_at: "2026-11-02T14:30:00.000Z",
    })
    expect(extractedLater.activityKind).toBe("Updated")
    expect(extractedLater.activityAt).toBe("2026-11-02T14:30:00.000Z")
  })

  it("keeps the completion time when it is the later of the two", () => {
    const completedLast = row({
      status: "completed",
      completed_at: "2026-11-02T15:00:00.000Z",
      updated_at: "2026-11-02T14:00:00.000Z",
    })
    expect(completedLast.activityKind).toBe("Completed")
    expect(completedLast.activityAt).toBe("2026-11-02T15:00:00.000Z")
  })

  it("falls back to the update time for a session that has not completed", () => {
    const active = row()
    expect(active.activityKind).toBe("Updated")
    expect(active.activityAt).toBe("2026-11-02T12:00:01.000Z")
  })

  it("does not call an abandoned session's end time a completion", () => {
    // The record `ibex_core.sessions_abandon_idle` writes: one statement sets
    // `status='abandoned'` and `completed_at=NOW()`, and the `sessions_updated_at`
    // BEFORE UPDATE trigger stamps `updated_at` to that same instant. The equal
    // timestamps therefore reach the terminal branch, and the label must agree
    // with the Abandoned pill beside it instead of claiming completion.
    const abandoned = row({
      status: "abandoned",
      completed_at: "2026-11-02T13:00:00.000Z",
      updated_at: "2026-11-02T13:00:00.000Z",
    })
    expect(abandoned.activityKind).not.toBe("Completed")
    expect(abandoned.activityKind).toBe("Abandoned")
    expect(abandoned.activityAt).toBe("2026-11-02T13:00:00.000Z")
  })

  it("labels a selected completed_at from the status, for every status in the schema", () => {
    const stamp = "2026-11-02T13:00:00.000Z"
    const labels = SESSION_STATUS_ORDER.map(
      (status) => [status, row({ status, completed_at: stamp, updated_at: stamp }).activityKind] as const,
    )
    expect(labels).toEqual([
      ["active", "Ended"],
      ["completed", "Completed"],
      ["abandoned", "Abandoned"],
      ["error", "Ended"],
    ])
  })

  it("still prefers the later update time for an abandoned record", () => {
    // The label follows the status; which timestamp wins is unchanged.
    const abandonedLaterUpdate = row({
      status: "abandoned",
      completed_at: "2026-11-02T13:00:00.000Z",
      updated_at: "2026-11-02T14:00:00.000Z",
    })
    expect(abandonedLaterUpdate.activityKind).toBe("Updated")
    expect(abandonedLaterUpdate.activityAt).toBe("2026-11-02T14:00:00.000Z")
  })
})

describe("session segments", () => {
  it("offers All plus only the statuses that occur, in a stable order", () => {
    const page = rows(
      session({ status: "error" }),
      session({ status: "active" }),
      session({ status: "active" }),
    )
    expect(sessionSegments(page)).toEqual([
      { id: "all", label: "All sessions", count: 3 },
      { id: "active", label: "Active", count: 2 },
      { id: "error", label: "Error", count: 1 },
    ])
  })

  it("omits a status with no rows and counts only what is loaded", () => {
    const page = rows(session({ status: "abandoned" }))
    expect(sessionSegments(page).map((segment) => segment.id)).toEqual(["all", "abandoned"])
  })

  it("has only All for an empty page", () => {
    expect(sessionSegments([])).toEqual([{ id: "all", label: "All sessions", count: 0 }])
  })

  it("segments rows without changing the source order", () => {
    const page = rows(session({ id: SESSION, status: "active" }), session({ status: "error" }))
    expect(segmentSessionRows(page, "all")).toHaveLength(2)
    expect(segmentSessionRows(page, "error")).toHaveLength(1)
    expect(segmentSessionRows(page, "completed")).toHaveLength(0)
  })
})

describe("session search", () => {
  it("matches the session id and the external id, case-insensitively", () => {
    const target = row()
    expect(matchesSessionSearch(target, "77777777")).toBe(true)
    expect(matchesSessionSearch(target, "EXT-1")).toBe(true)
    expect(matchesSessionSearch(target, "no-such-session")).toBe(false)
  })

  it("treats a blank query as no filter", () => {
    expect(matchesSessionSearch(row(), "   ")).toBe(true)
  })

  it("does not match a row with no external id", () => {
    expect(matchesSessionSearch(row({ external_id: null }), "ext-1")).toBe(false)
  })
})

describe("session page filters", () => {
  it("filters by model and provider", () => {
    const page = rows(
      session({ model: "gpt-4.1", provider: "openai" }),
      session({ model: "claude-sonnet-4", provider: "anthropic" }),
    )
    expect(filterSessionRows(page, filters({ model: "claude-sonnet-4" }))).toHaveLength(1)
    expect(filterSessionRows(page, filters({ provider: "openai" }))).toHaveLength(1)
    expect(filterSessionRows(page, filters({ model: "gpt-4.1", provider: "anthropic" }))).toHaveLength(0)
  })

  it("places each latency on exactly one side of a bucket boundary", () => {
    const under = rows(session({ total_latency_ms: 999 }))
    const edge = rows(session({ total_latency_ms: 1_000 }))
    const middle = rows(session({ total_latency_ms: 9_999 }))
    const over = rows(session({ total_latency_ms: 10_000 }))
    expect(filterSessionRows(under, filters({ duration: "under-1s" }))).toHaveLength(1)
    expect(filterSessionRows(edge, filters({ duration: "under-1s" }))).toHaveLength(0)
    expect(filterSessionRows(edge, filters({ duration: "1s-to-10s" }))).toHaveLength(1)
    expect(filterSessionRows(middle, filters({ duration: "1s-to-10s" }))).toHaveLength(1)
    expect(filterSessionRows(over, filters({ duration: "over-10s" }))).toHaveLength(1)
  })

  it("counts the active page filters", () => {
    expect(sessionPageFilterCount(DEFAULT_SESSION_PAGE_FILTERS)).toBe(0)
    expect(sessionPageFilterCount(filters({ search: "  " }))).toBe(0)
    expect(sessionPageFilterCount(filters({ search: "77777777", model: "gpt-4.1" }))).toBe(2)
    expect(
      sessionPageFilterCount(filters({ search: "x", model: "m", provider: "p", duration: "over-10s" })),
    ).toBe(4)
  })

  it("counts the request-scoped filters together with the page-scoped ones", () => {
    expect(activeSessionFilterCount(DEFAULT_SESSION_PAGE_FILTERS, { status: null, agentId: null })).toBe(0)
    expect(activeSessionFilterCount(filters({ model: "gpt-4.1" }), { status: "error", agentId: null })).toBe(2)
    expect(
      activeSessionFilterCount(filters({ search: "x", provider: "openai" }), {
        status: null,
        agentId: AGENT,
      }),
    ).toBe(3)
  })

  it("lists the distinct facet values that occur on the page", () => {
    const page = rows(
      session({ model: "gpt-4.1", provider: "openai" }),
      session({ model: "claude-sonnet-4", provider: "openai" }),
      session({ model: "gpt-4.1", provider: "anthropic" }),
    )
    expect(sessionFacets(page, "model")).toEqual(["claude-sonnet-4", "gpt-4.1"])
    expect(sessionFacets(page, "provider")).toEqual(["anthropic", "openai"])
  })
})

describe("agent filter options", () => {
  it("labels an agent with its name and slug", () => {
    expect(agentFilterOptions([agent()], null)).toEqual([
      { value: AGENT, label: "Support Agent · support-agent" },
    ])
  })

  it("keeps a selected agent that the loaded page does not carry", () => {
    const options = agentFilterOptions([agent()], MISSING_AGENT)
    expect(options).toHaveLength(2)
    expect(options[0]?.value).toBe(MISSING_AGENT)
    expect(options[0]?.label).toContain("not in this agent page")
  })

  it("does not duplicate a selected agent the page already carries", () => {
    expect(agentFilterOptions([agent()], AGENT)).toHaveLength(1)
  })
})

describe("agent id entry path", () => {
  it("accepts a full UUID and lowercases it for the query", () => {
    expect(parseAgentIdFilter(MISSING_AGENT)).toBe(MISSING_AGENT)
    expect(parseAgentIdFilter(`  ${MISSING_AGENT.toUpperCase()}  `)).toBe(MISSING_AGENT)
  })

  it("refuses anything that is not a complete UUID", () => {
    // A partial id would be a request the API answers with a validation error,
    // and a truncated short-id is what the table displays, not an identifier.
    expect(parseAgentIdFilter("")).toBeNull()
    expect(parseAgentIdFilter("99999999")).toBeNull()
    expect(parseAgentIdFilter("99999999-9999-4999-8999-99999999999")).toBeNull()
    expect(parseAgentIdFilter(`${MISSING_AGENT}0`)).toBeNull()
    expect(parseAgentIdFilter("support-agent")).toBeNull()
    expect(parseAgentIdFilter("/sessions?agent_id=x")).toBeNull()
    expect(parseAgentIdFilter("99999999-9999-4999-8999-99999999999z")).toBeNull()
  })

  it("names the accepted shape in the error copy", () => {
    expect(AGENT_ID_FILTER_INVALID).toContain("33333333-3333-4333-8333-333333333333")
    expect(AGENT_ID_FILTER_INVALID).toContain("full agent UUID")
  })

  it("keeps the typed id selected in the control after the filter is applied", () => {
    const options = agentFilterOptions([agent()], MISSING_AGENT)
    expect(options.some((option) => option.value === MISSING_AGENT)).toBe(true)
  })
})

describe("session columns", () => {
  it("shows extraction by default and leaves tokens to the column control", () => {
    expect(DEFAULT_SESSION_COLUMNS).toEqual(["extraction"])
    expect(sessionColumnVisible(DEFAULT_SESSION_COLUMNS, "extraction")).toBe(true)
    expect(sessionColumnVisible(DEFAULT_SESSION_COLUMNS, "tokens")).toBe(false)
  })

  it("toggles a column off and back on in the canonical order", () => {
    const withoutExtraction = toggleSessionColumn(DEFAULT_SESSION_COLUMNS, "extraction")
    expect(withoutExtraction).toEqual([])
    expect(sessionColumnVisible(withoutExtraction, "extraction")).toBe(false)
    expect(toggleSessionColumn(withoutExtraction, "extraction")).toEqual(["extraction"])
    expect(toggleSessionColumn(withoutExtraction, "tokens")).toEqual(["tokens"])
  })

  it("keeps the canonical order when a second column is enabled", () => {
    expect(toggleSessionColumn(["tokens"], "extraction")).toEqual(["extraction", "tokens"])
  })
})
