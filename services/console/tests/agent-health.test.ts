import { describe, expect, it } from "vitest"

import {
  AGENT_ERROR_BAND_PCT,
  AGENT_RETRY_BAND,
  agentDetails,
  getAgentHealth,
  type AgentHealthInput,
  type AgentSummary,
} from "../app/lib/agent-preview"

const AGENT_TIME = "2026-10-30T13:00:00.000Z"

function inputFor(agent: AgentSummary): AgentHealthInput {
  return {
    id: agent.id,
    name: agent.name,
    status: agent.status,
    errorRate: agent.stats.errorRate,
    failedRuns: agent.stats.failed,
    errorBandPct: agent.errorBandPct,
    retriesPerRun: agent.stats.retriesPerRun,
    retryBand: agent.retryBand,
    budget: agent.budget,
    drift: agent.drift,
    coveragePct: agent.stats.coveragePct,
    coverageRuns: agent.stats.coverageRuns,
    coverageTotal: agent.stats.coverageTotal,
    coverageTargetPct: agent.coverageTargetPct,
    p95Ms: agent.stats.p95Ms,
    latencyBudgetMs: agent.latencyBudgetMs,
    quarantined: agent.stats.quarantined,
    lastDeployFailed: agent.healthReasons.some((reason) => reason.code === "deploy_failed"),
    runs: agent.stats.runs,
    hasEverRun: agent.stats.lastRun !== null,
    suspendedReason: agent.status === "suspended" ? "Policy suspension" : null,
    at: agent.stats.lastRun?.at ?? AGENT_TIME,
  }
}

function findAgent(name: string): AgentSummary {
  const agent = agentDetails.find((candidate) => candidate.name === name)
  if (!agent) throw new Error(`Missing agent test fixture: ${name}`)
  return agent
}

describe("getAgentHealth", () => {
  it("marks Support triage as needing attention when retries exceed the band", () => {
    const result = getAgentHealth(inputFor(findAgent("Support triage")))
    expect(result.health).toBe("attention")
    expect(result.attention.map((reason) => reason.code)).toContain("retries")
  })

  it("marks Research assistant as needing attention when budget headroom is below its floor", () => {
    const result = getAgentHealth(inputFor(findAgent("Research assistant")))
    expect(result.health).toBe("attention")
    expect(result.attention.map((reason) => reason.code)).toContain("budget_floor")
  })

  it("marks Policy reviewer as needing attention when drift is advisory", () => {
    const result = getAgentHealth(inputFor(findAgent("Policy reviewer")))
    expect(result.health).toBe("attention")
    expect(result.attention.map((reason) => reason.code)).toContain("drift")
  })

  it("keeps Billing analyst healthy when all measured signals are within bands", () => {
    const result = getAgentHealth(inputFor(findAgent("Billing analyst")))
    expect(result.health).toBe("healthy")
    expect(result.attention).toHaveLength(0)
  })

  it.each([
    ["archived", "archived"],
    ["paused", "paused"],
    ["draining", "paused"],
    ["suspended", "failing"],
  ] as const)("respects lifecycle priority for %s agents", (status, expected) => {
    const input = inputFor(findAgent("Billing analyst"))
    const result = getAgentHealth({ ...input, status })
    expect(result.health).toBe(expected)
  })

  it("treats an error rate above twice its band as failing", () => {
    const input = inputFor(findAgent("Billing analyst"))
    const result = getAgentHealth({
      ...input,
      errorRate: AGENT_ERROR_BAND_PCT * 2 + 0.1,
    })
    expect(result.health).toBe("failing")
    expect(result.attention.map((reason) => reason.code)).toContain("error_rate")
  })

  it("does not call an agent with no runs in range healthy when it has never run", () => {
    const input = inputFor(findAgent("Returns concierge"))
    const result = getAgentHealth(input)
    expect(result.health).toBe("no_data")
    expect(result.healthReasons.map((reason) => reason.code)).toContain("no_data")
    expect(result.attention).toHaveLength(0)
  })

  it("keeps the health healthy when the selected range has no runs but the agent ran historically", () => {
    const input = inputFor(findAgent("Billing analyst"))
    const result = getAgentHealth({ ...input, runs: 0, errorRate: null, failedRuns: 0 })
    expect(result.health).toBe("healthy")
    expect(result.healthReasons.map((reason) => reason.code)).not.toContain("no_data")
  })

  it("promotes every non-critical health signal to attention", () => {
    const input = inputFor(findAgent("Billing analyst"))
    const result = getAgentHealth({
      ...input,
      retriesPerRun: AGENT_RETRY_BAND + 0.1,
    })
    expect(result.health).toBe("attention")
    expect(result.attention.map((reason) => reason.code)).toContain("retries")
  })
})
