import { describe, expect, it } from "vitest"

import {
  defaultLiveDirectiveListQuery,
  LiveDirectiveQueryError,
  parseLiveDirectiveDetailQuery,
  parseLiveDirectiveListQuery,
  parseLiveDirectiveListQueryLenient,
  serializeLiveDirectiveDetailQuery,
  serializeLiveDirectiveListQuery,
} from "../shared/operator/directive-query"

const AGENT = "11111111-1111-4111-8111-111111111111"

describe("live directive query codecs", () => {
  it("defaults to every directive on the first page", () => {
    expect(parseLiveDirectiveListQuery(new URLSearchParams())).toEqual(
      defaultLiveDirectiveListQuery(),
    )
    expect(parseLiveDirectiveDetailQuery(new URLSearchParams())).toEqual({ range: "7d" })
  })

  it("round-trips the list filters", () => {
    const query = { state: "active", agentId: AGENT, cursor: "cursor-1", limit: 25 } as const
    expect(parseLiveDirectiveListQuery(serializeLiveDirectiveListQuery(query))).toEqual(query)
  })

  it("round-trips the usage range", () => {
    for (const range of ["24h", "7d", "30d"] as const) {
      expect(parseLiveDirectiveDetailQuery(serializeLiveDirectiveDetailQuery({ range }))).toEqual({
        range,
      })
    }
  })

  it("rejects unknown fields, a bad state, and a bad range", () => {
    expect(() => parseLiveDirectiveListQuery({ sort: "name" })).toThrow(LiveDirectiveQueryError)
    expect(() => parseLiveDirectiveListQuery({ state: "draining" })).toThrow(LiveDirectiveQueryError)
    expect(() => parseLiveDirectiveListQuery({ agent_id: "agt_1" })).toThrow(LiveDirectiveQueryError)
    expect(() => parseLiveDirectiveDetailQuery({ range: "90d" })).toThrow(LiveDirectiveQueryError)
    expect(() => parseLiveDirectiveDetailQuery({ from: "v1" })).toThrow(LiveDirectiveQueryError)
  })

  it("keeps what parses and drops the rest so the URL can be rewritten", () => {
    expect(
      parseLiveDirectiveListQueryLenient({ state: "active", agent_id: "nope", limit: "101" }),
    ).toEqual({ ...defaultLiveDirectiveListQuery(), state: "active" })
  })
})
