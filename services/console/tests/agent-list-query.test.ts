import { describe, expect, it } from "vitest"

import {
  activeAgentFilterChips,
  agentIsNearBudget,
  agentNeedsAttention,
  agentViewCounts,
  filterAgents,
  groupAgents,
  sortAgents,
} from "../app/lib/agent-list"
import {
  AGENT_DEFAULT_SORT_DIRECTION,
  agentListHref,
  emptyAgentListState,
  parseAgentListQuery,
  serializeAgentListQuery,
  type AgentListState,
} from "../app/lib/agent-list-query"
import {
  agentStatusCounts,
  agentSummaries,
  agentTotals,
  agentBudgetLeftPct,
  sortAttention,
} from "../app/lib/agent-preview"

function stateWith(patch: Partial<AgentListState>): AgentListState {
  return { ...emptyAgentListState(), ...patch }
}

describe("agent list query", () => {
  it("starts from the default view", () => {
    const state = parseAgentListQuery({})
    expect(state).toEqual(emptyAgentListState())
    expect(agentListHref(state)).toBe("/agents")
  })

  it("round-trips every supported filter through the URL", () => {
    const state = stateWith({
      search: "support",
      view: "attention",
      statuses: ["active", "paused"],
      envs: ["production"],
      models: ["claude-sonnet-4"],
      owners: ["Platform"],
      healths: ["attention", "failing"],
      sort: "runs",
      direction: "desc",
      group: "owner",
      density: "compact",
      includeNoData: true,
    })
    const href = agentListHref(state)
    const parsed = parseAgentListQuery(Object.fromEntries(new URL(href, "http://x").searchParams))
    expect(parsed).toEqual(state)
  })

  it("drops values that are not part of the contract", () => {
    const parsed = parseAgentListQuery({
      q: "  support  ",
      view: "exploded",
      status: "active,deleted,bogus",
      env: "production,qa",
      health: "failing",
      sort: "nonsense",
      dir: "sideways",
      density: "huge",
    })
    expect(parsed.search).toBe("support")
    expect(parsed.view).toBe("all")
    expect(parsed.statuses).toEqual(["active"])
    expect(parsed.envs).toEqual(["production"])
    expect(parsed.healths).toEqual(["failing"])
    expect(parsed.sort).toBe("health")
    expect(parsed.direction).toBe("asc")
    expect(parsed.density).toBe("comfortable")
  })

  it("keeps the legacy attention parameter working", () => {
    expect(parseAgentListQuery({ attention: "1" }).view).toBe("attention")
  })

  it("does not serialize the default direction for a custom sort", () => {
    const params = serializeAgentListQuery(stateWith({ sort: "runs", direction: "desc" }))
    expect(params.get("sort")).toBe("runs")
    expect(params.get("dir")).toBeNull()
    expect(AGENT_DEFAULT_SORT_DIRECTION.runs).toBe("desc")
    expect(params.get("dir")).toBeNull()
  })

  it("serializes a non-default direction", () => {
    const params = serializeAgentListQuery(stateWith({ sort: "runs", direction: "asc" }))
    expect(params.get("dir")).toBe("asc")
  })
})

describe("agent list filtering and sorting", () => {
  it("matches search against the identity, not the raw record", () => {
    const state = stateWith({ search: "support triage" })
    expect(filterAgents(agentSummaries, state).map((agent) => agent.name)).toEqual(["Support triage"])
  })

  it("hides agents without data unless the view or toggle asks for them", () => {
    const hidden = filterAgents(agentSummaries, stateWith({}))
    expect(hidden).toHaveLength(agentTotals.agentsWithData)
    expect(hidden.every((agent) => agent.stats.runs > 0)).toBe(true)

    const all = filterAgents(agentSummaries, stateWith({ includeNoData: true }))
    expect(all).toHaveLength(agentSummaries.length)
  })

  it("counts the attention view by agents, not by attention reasons", () => {
    const attention = filterAgents(agentSummaries, stateWith({ view: "attention" }))
    expect(attention).toHaveLength(agentTotals.needsAttention)
    expect(attention).toHaveLength(agentSummaries.filter(agentNeedsAttention).length)
    const reasons = agentSummaries.reduce((total, agent) => total + agent.attention.length, 0)
    expect(reasons).toBeGreaterThan(attention.length)
  })

  it("exposes the same counts in the header and the quick views", () => {
    const counts = agentViewCounts(agentSummaries)
    expect(counts.all).toBe(24)
    expect(counts.attention).toBe(agentTotals.needsAttention)
    expect(counts.budget).toBe(agentSummaries.filter(agentIsNearBudget).length)
    expect(counts.paused).toBe(
      agentSummaries.filter((agent) => agent.status === "paused" || agent.status === "draining").length,
    )
  })

  it("sorts health worst-first and breaks ties by run volume", () => {
    const sorted = sortAgents(agentSummaries, "health", "asc")
    expect(sorted[0]?.health).toBe("failing")
    expect(sorted.filter((agent) => agent.health === "attention")).toHaveLength(
      agentSummaries.filter((agent) => agent.health === "attention").length,
    )
    expect(sorted.at(-1)?.health).toBe("no_data")
  })

  it("sorts budget headroom ascending using committed spend", () => {
    const sorted = sortAgents(agentSummaries, "budget", "asc")
    const withBudget = sorted.filter((agent) => agent.budget)
    for (let index = 1; index < withBudget.length; index += 1) {
      const previous = agentBudgetLeftPct(withBudget[index - 1]!.budget!)
      const current = agentBudgetLeftPct(withBudget[index]!.budget!)
      expect(previous).toBeLessThanOrEqual(current)
    }
  })

  it("groups without losing or duplicating agents", () => {
    for (const key of ["owner", "env", "health"] as const) {
      const groups = groupAgents(agentSummaries, key)
      const total = groups.reduce((sum, group) => sum + group.agents.length, 0)
      expect(total).toBe(agentSummaries.length)
      expect(new Set(groups.map((group) => group.key)).size).toBe(groups.length)
    }
  })

  it("orders attention reasons by severity", () => {
    const battery = agentSummaries.flatMap((agent) => agent.attention)
    const sorted = sortAttention(battery)
    expect(sorted).toHaveLength(battery.length)
  })

  it("removes exactly the chip it represents", () => {
    const state = stateWith({
      view: "attention",
      statuses: ["active"],
      envs: ["production"],
      healths: ["attention"],
      includeNoData: true,
    })
    const chips = activeAgentFilterChips(state)
    expect(chips).toHaveLength(5)
    for (const chip of chips) {
      expect(activeAgentFilterChips(chip.next).length).toBeLessThan(chips.length)
    }
  })
})

describe("agent aggregates", () => {
  it("matches the fixture totals the list header reports", () => {
    expect(agentStatusCounts.total).toBe(24)
    expect(agentStatusCounts.active).toBe(21)
    expect(agentStatusCounts.paused).toBe(2)
    expect(agentStatusCounts.suspended).toBe(1)
    expect(agentTotals.agentsWithData).toBe(10)
    expect(agentTotals.runs).toBe(12_140)
    expect(agentTotals.spendUsd).toBe(10_210)
    expect(agentTotals.needsAttention).toBe(6)
  })

  it("computes the weighted error rate from recorded failures", () => {
    const failures = agentSummaries.reduce((total, agent) => total + agent.stats.failed, 0)
    expect(failures).toBe(202)
    expect(agentTotals.errorRate).toBeCloseTo((failures / agentTotals.runs) * 100, 1)
  })
})
