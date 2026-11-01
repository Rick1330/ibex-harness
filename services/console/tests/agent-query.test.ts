import { describe, expect, it } from "vitest"

import {
  agentQueryKey,
  defaultLiveAgentQuery,
  LiveAgentQueryError,
  parseLiveAgentQuery,
  serializeLiveAgentQuery,
  serializeLiveAgentUrlQuery,
  type LiveAgentQuery,
} from "../shared/operator/agent-query"

const full: LiveAgentQuery = {
  search: "support",
  status: "paused",
  tags: ["prod", "billing"],
  cursor: "cursor-1",
  limit: 25,
}

describe("live agent query codec", () => {
  it("defaults to an unfiltered first page", () => {
    expect(parseLiveAgentQuery(new URLSearchParams())).toEqual(defaultLiveAgentQuery())
    expect(defaultLiveAgentQuery()).toEqual({
      search: null,
      status: null,
      tags: [],
      cursor: null,
      limit: 50,
    })
  })

  it("parses and trims every bounded field", () => {
    const parsed = parseLiveAgentQuery({
      search: "  support  ",
      status: "active",
      tags: " prod, billing ,prod ",
      cursor: "abc",
      limit: "10",
    })
    expect(parsed).toEqual({
      search: "support",
      status: "active",
      tags: ["prod", "billing"],
      cursor: "abc",
      limit: 10,
    })
  })

  it("serializes repeated tags for the API and a readable URL for the browser", () => {
    expect(serializeLiveAgentQuery(full).toString()).toBe(
      "limit=25&search=support&status=paused&cursor=cursor-1&tags=prod&tags=billing",
    )
    expect(serializeLiveAgentUrlQuery(full).toString()).toBe(
      "limit=25&search=support&status=paused&cursor=cursor-1&tags=prod%2Cbilling",
    )
  })

  it("round-trips the browser form", () => {
    const url = serializeLiveAgentUrlQuery(full)
    expect(parseLiveAgentQuery(new URLSearchParams(url))).toEqual(full)
  })

  it("keys equal queries identically", () => {
    expect(agentQueryKey(full)).toBe(agentQueryKey({ ...full, tags: [...full.tags] }))
    expect(agentQueryKey(full)).not.toBe(agentQueryKey({ ...full, limit: 50 }))
  })

  it("rejects unknown fields instead of silently ignoring filters", () => {
    expect(() => parseLiveAgentQuery({ view: "attention" })).toThrow(LiveAgentQueryError)
  })

  it("rejects an unknown status", () => {
    expect(() => parseLiveAgentQuery({ status: "draining" })).toThrow(LiveAgentQueryError)
  })

  it("rejects out-of-range limits", () => {
    for (const limit of ["0", "101", "1.5", "many"]) {
      expect(() => parseLiveAgentQuery({ limit }), limit).toThrow(LiveAgentQueryError)
    }
  })

  it("bounds tag count and length", () => {
    const tooMany = Array.from({ length: 33 }, (_, index) => `tag-${index}`).join(",")
    expect(() => parseLiveAgentQuery({ tags: tooMany })).toThrow(LiveAgentQueryError)
    expect(() => parseLiveAgentQuery({ tags: "a".repeat(65) })).toThrow(LiveAgentQueryError)
  })

  it("rejects cursor whitespace and oversized search", () => {
    expect(() => parseLiveAgentQuery({ cursor: "has space" })).toThrow(LiveAgentQueryError)
    expect(() => parseLiveAgentQuery({ search: "a".repeat(201) })).toThrow(LiveAgentQueryError)
  })
})
