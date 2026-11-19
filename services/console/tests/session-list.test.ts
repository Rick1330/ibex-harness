import { describe, expect, it } from "vitest"

import {
  DEFAULT_SESSION_COLUMNS,
  DEFAULT_SESSION_PAGE_FILTERS,
  agentFilterOptions,
  filterSessionRows,
  formatSessionLatency,
  matchesSessionSearch,
  segmentSessionRows,
  sessionColumnVisible,
  sessionCoverage,
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

describe("session coverage", () => {
  it("reports the extracted turn over the turn count as the contract states it", () => {
    expect(sessionCoverage(0, 1)).toEqual({ label: "0 / 1", percent: 0 })
    expect(sessionCoverage(3, 4)).toEqual({ label: "3 / 4", percent: 75 })
  })

  it("does not inflate a zero-based index into a count", () => {
    // `last_extracted_turn` is compared literally: no `+1`, no rounding up.
    expect(sessionCoverage(0, 5).percent).toBe(0)
  })

  it("has no percentage when the session recorded no turns", () => {
    const covered = row({ turn_count: 0, last_extracted_turn: 0 })
    expect(covered.coverageLabel).toBe("0 / 0")
    expect(covered.coveragePercent).toBeNull()
    expect(covered.coverageNote).toBe("No turns recorded")
  })

  it("clamps the percentage but reports the raw ratio", () => {
    expect(sessionCoverage(5, 3)).toEqual({ label: "5 / 3", percent: 100 })
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
  it("uses the completion time when the session is complete", () => {
    const completed = row({ status: "completed", completed_at: "2026-11-02T13:00:00.000Z" })
    expect(completed.activityKind).toBe("Ended")
    expect(completed.activityAt).toBe("2026-11-02T13:00:00.000Z")
  })

  it("falls back to the update time for a session that has not completed", () => {
    const active = row()
    expect(active.activityKind).toBe("Updated")
    expect(active.activityAt).toBe("2026-11-02T12:00:01.000Z")
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

describe("session columns", () => {
  it("shows coverage by default and leaves tokens to the column control", () => {
    expect(DEFAULT_SESSION_COLUMNS).toEqual(["coverage"])
    expect(sessionColumnVisible(DEFAULT_SESSION_COLUMNS, "coverage")).toBe(true)
    expect(sessionColumnVisible(DEFAULT_SESSION_COLUMNS, "tokens")).toBe(false)
  })

  it("toggles a column off and back on in the canonical order", () => {
    const withoutCoverage = toggleSessionColumn(DEFAULT_SESSION_COLUMNS, "coverage")
    expect(withoutCoverage).toEqual([])
    expect(sessionColumnVisible(withoutCoverage, "coverage")).toBe(false)
    expect(toggleSessionColumn(withoutCoverage, "coverage")).toEqual(["coverage"])
    expect(toggleSessionColumn(withoutCoverage, "tokens")).toEqual(["tokens"])
  })

  it("keeps the canonical order when a second column is enabled", () => {
    expect(toggleSessionColumn(["tokens"], "coverage")).toEqual(["coverage", "tokens"])
  })
})
