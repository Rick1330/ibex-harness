import { describe, expect, it } from "vitest"

import {
  defaultLiveMemoryQuery,
  LiveMemoryQueryError,
  parseLiveMemoryQuery,
  serializeLiveMemoryQuery,
  type LiveMemoryQuery,
} from "../shared/operator/memory-query"

const AGENT = "11111111-1111-4111-8111-111111111111"
const SESSION = "22222222-2222-4222-8222-222222222222"

const full: LiveMemoryQuery = {
  agentId: AGENT,
  sessionId: SESSION,
  status: "quarantined",
  category: "behavioral",
  cursor: "cursor-1",
  limit: 25,
}

describe("live memory query codec", () => {
  it("defaults to an unfiltered first page", () => {
    expect(parseLiveMemoryQuery(new URLSearchParams())).toEqual(defaultLiveMemoryQuery())
    expect(defaultLiveMemoryQuery()).toEqual({
      agentId: null,
      sessionId: null,
      status: null,
      category: null,
      cursor: null,
      limit: 50,
    })
  })

  it("parses and lowercases UUID filters", () => {
    const parsed = parseLiveMemoryQuery({
      agent_id: AGENT.toUpperCase(),
      session_id: SESSION,
      status: "active",
      category: "factual",
      limit: "10",
    })
    expect(parsed).toEqual({
      agentId: AGENT,
      sessionId: SESSION,
      status: "active",
      category: "factual",
      cursor: null,
      limit: 10,
    })
  })

  it("round-trips the serialized query", () => {
    expect(parseLiveMemoryQuery(serializeLiveMemoryQuery(full))).toEqual(full)
    expect(serializeLiveMemoryQuery(full).toString()).toContain("agent_id=" + AGENT)
  })

  it("rejects unknown fields", () => {
    expect(() => parseLiveMemoryQuery({ view: "attention" })).toThrow(LiveMemoryQueryError)
  })

  it("rejects malformed UUIDs", () => {
    expect(() => parseLiveMemoryQuery({ agent_id: "agent-1" })).toThrow(LiveMemoryQueryError)
    expect(() => parseLiveMemoryQuery({ session_id: "1" })).toThrow(LiveMemoryQueryError)
  })

  it("rejects unknown status and category", () => {
    expect(() => parseLiveMemoryQuery({ status: "draining" })).toThrow(LiveMemoryQueryError)
    expect(() => parseLiveMemoryQuery({ category: "random" })).toThrow(LiveMemoryQueryError)
  })

  it("rejects invalid limits and cursor whitespace", () => {
    for (const limit of ["0", "101", "1.5", "many"]) {
      expect(() => parseLiveMemoryQuery({ limit }), limit).toThrow(LiveMemoryQueryError)
    }
    expect(() => parseLiveMemoryQuery({ cursor: "has space" })).toThrow(LiveMemoryQueryError)
  })
})
