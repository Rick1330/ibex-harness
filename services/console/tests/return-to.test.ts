import { describe, expect, it } from "vitest"

import { agentReturnLabel, safeAgentReturn, safeExploreReturn } from "../app/lib/return-to"

const SESSION = "77777777-7777-4777-8777-777777777777"
const MEMORY = "44444444-4444-4444-8444-444444444444"

describe("explore return target", () => {
  it("accepts only local explore paths", () => {
    expect(safeExploreReturn("/explore?limit=10")).toBe("/explore?limit=10")
    expect(safeExploreReturn("/explore/t/trace-a")).toBe("/explore/t/trace-a")
    expect(safeExploreReturn("https://evil.example")).toBe("/explore")
    expect(safeExploreReturn("//evil.example")).toBe("/explore")
    expect(safeExploreReturn("javascript:alert(1)")).toBe("/explore")
    expect(safeExploreReturn(undefined)).toBe("/explore")
  })

  it("accepts the record page a trace link came from", () => {
    // A session turn links to Explore with the session as its back target; a
    // memory provenance link does the same for the memory.
    expect(safeExploreReturn(`/sessions/${SESSION}`)).toBe(`/sessions/${SESSION}`)
    expect(safeExploreReturn(`/sessions/${SESSION}?return=%2Fsessions%3Fstatus%3Derror`)).toBe(
      `/sessions/${SESSION}?return=%2Fsessions%3Fstatus%3Derror`,
    )
    expect(safeExploreReturn(`/memories/${MEMORY}`)).toBe(`/memories/${MEMORY}`)
  })

  it("rejects record-shaped paths that are not a checked record id", () => {
    expect(safeExploreReturn("/sessions")).toBe("/explore")
    expect(safeExploreReturn("/sessions/not-a-uuid")).toBe("/explore")
    expect(safeExploreReturn(`/sessions/${SESSION}/../secrets`)).toBe("/explore")
    expect(safeExploreReturn(`/sessions/${SESSION}#frag`)).toBe("/explore")
    expect(safeExploreReturn(`//sessions/${SESSION}`)).toBe("/explore")
    expect(safeExploreReturn(`/admin/${SESSION}`)).toBe("/explore")
  })
})

describe("agent return target", () => {
  it("defaults to the agents list", () => {
    expect(safeAgentReturn(undefined)).toBe("/agents")
    expect(safeAgentReturn("https://evil.example")).toBe("/agents")
    expect(safeAgentReturn("//evil.example")).toBe("/agents")
  })

  it("accepts the agents list a row came from", () => {
    expect(safeAgentReturn("/agents")).toBe("/agents")
    expect(safeAgentReturn("/agents?status=active")).toBe("/agents?status=active")
  })

  it("accepts the checked sessions list a session row came from", () => {
    // A session row links to its agent with the Sessions list as the return
    // target; the back link has to land there, not on /agents.
    expect(safeAgentReturn("/sessions")).toBe("/sessions")
    expect(safeAgentReturn("/sessions?limit=50&status=error")).toBe("/sessions?limit=50&status=error")
    expect(safeAgentReturn(`/sessions?limit=50&agent_id=${SESSION}`)).toBe(`/sessions?limit=50&agent_id=${SESSION}`)
  })

  it("does not widen the allowlist to records, fragments or other paths", () => {
    expect(safeAgentReturn(`/sessions/${SESSION}`)).toBe("/agents")
    expect(safeAgentReturn("/sessions?status=error#frag")).toBe("/agents")
    expect(safeAgentReturn("/sessions-and-more")).toBe("/agents")
    expect(safeAgentReturn("/sessions/../agents")).toBe("/agents")
    expect(safeAgentReturn(`//sessions?limit=50`)).toBe("/agents")
    expect(safeAgentReturn(`/agents/${SESSION}`)).toBe("/agents")
    expect(safeAgentReturn("/memories")).toBe("/agents")
    expect(safeAgentReturn("/explore?limit=10")).toBe("/agents")
  })

  it("labels the back link with its destination", () => {
    expect(agentReturnLabel(safeAgentReturn("/sessions?limit=50"))).toBe("Back to sessions")
    expect(agentReturnLabel(safeAgentReturn(`/sessions/${SESSION}`))).toBe("Back to agents")
    expect(agentReturnLabel(safeAgentReturn("/agents?status=active"))).toBe("Back to agents")
    expect(agentReturnLabel(safeAgentReturn(undefined))).toBe("Back to agents")
  })
})
