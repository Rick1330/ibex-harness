import { describe, expect, it } from "vitest"

import {
  defaultLiveSessionQuery,
  LiveSessionQueryError,
  parseLiveSessionQuery,
  serializeLiveSessionQuery,
  type LiveSessionQuery,
} from "../shared/operator/session-query"

const AGENT = "11111111-1111-4111-8111-111111111111"

const full: LiveSessionQuery = {
  agentId: AGENT,
  status: "completed",
  cursor: "cursor-1",
  limit: 25,
}

describe("live session query codec", () => {
  it("defaults to an unfiltered first page", () => {
    expect(parseLiveSessionQuery(new URLSearchParams())).toEqual(defaultLiveSessionQuery())
    expect(defaultLiveSessionQuery()).toEqual({
      agentId: null,
      status: null,
      cursor: null,
      limit: 50,
    })
  })

  it("parses and lowercases the agent filter", () => {
    expect(
      parseLiveSessionQuery({
        agent_id: AGENT.toUpperCase(),
        status: "error",
        limit: "10",
      }),
    ).toEqual({
      agentId: AGENT,
      status: "error",
      cursor: null,
      limit: 10,
    })
  })

  it("round-trips the serialized query", () => {
    expect(parseLiveSessionQuery(serializeLiveSessionQuery(full))).toEqual(full)
    expect(serializeLiveSessionQuery(full).toString()).toContain(`agent_id=${AGENT}`)
  })

  it("rejects unknown fields", () => {
    expect(() => parseLiveSessionQuery({ view: "timeline" })).toThrow(LiveSessionQueryError)
  })

  it("rejects a malformed agent UUID", () => {
    expect(() => parseLiveSessionQuery({ agent_id: "agent-1" })).toThrow(LiveSessionQueryError)
  })

  it("rejects an unknown status", () => {
    expect(() => parseLiveSessionQuery({ status: "draining" })).toThrow(LiveSessionQueryError)
  })

  it("rejects invalid limits and cursor whitespace", () => {
    for (const limit of ["0", "101", "1.5", "many"]) {
      expect(() => parseLiveSessionQuery({ limit }), limit).toThrow(LiveSessionQueryError)
    }
    expect(() => parseLiveSessionQuery({ cursor: "has space" })).toThrow(LiveSessionQueryError)
  })
})
