import { describe, expect, it } from "vitest"
import {
  OVERVIEW_DEFAULT,
  PLATFORM_DEFAULT,
  overviewHref,
  parseOverviewQuery,
  parsePlatformQuery,
  parsePolicyListQuery,
  parsePolicyRuleDetailQuery,
  platformHref,
  policyListHref,
  serializeOverviewQuery,
  serializePlatformQuery,
  serializePolicyListQuery,
} from "../app/lib/govern-query"
import { policySnapshots } from "../app/lib/policy-preview"

const CURRENT_SNAPSHOT = policySnapshots[0]!.id
const PREVIOUS_SNAPSHOT = policySnapshots[1]!.id

describe("policy list query", () => {
  it("defaults to the newest snapshot", () => {
    expect(parsePolicyListQuery({})).toEqual({
      snapshot: CURRENT_SNAPSHOT,
      q: "",
      effect: "all",
      mode: "all",
      scope: "all",
    })
  })

  it("accepts a known historical snapshot and drops unknown ones", () => {
    expect(parsePolicyListQuery({ snapshot: PREVIOUS_SNAPSHOT }).snapshot).toBe(PREVIOUS_SNAPSHOT)
    expect(parsePolicyListQuery({ snapshot: "pol_1999" }).snapshot).toBe(CURRENT_SNAPSHOT)
  })

  it("validates effect and mode filters", () => {
    const state = parsePolicyListQuery({ effect: "require_approval", mode: "advisory", scope: "org_demo_42 · content", q: "refund" })
    expect(state).toMatchObject({ effect: "require_approval", mode: "advisory", scope: "org_demo_42 · content", q: "refund" })
    expect(parsePolicyListQuery({ effect: "explode", mode: "hard" })).toMatchObject({ effect: "all", mode: "all" })
  })

  it("round-trips and keeps the default href clean", () => {
    const state = parsePolicyListQuery({ snapshot: PREVIOUS_SNAPSHOT, mode: "enforced" })
    expect(serializePolicyListQuery(state).toString()).toBe(`snapshot=${PREVIOUS_SNAPSHOT}&mode=enforced`)
    expect(policyListHref(state)).toBe(`/policies?snapshot=${PREVIOUS_SNAPSHOT}&mode=enforced`)
    expect(policyListHref(parsePolicyListQuery({}))).toBe("/policies")
  })
})

describe("policy rule detail query", () => {
  it("keeps a valid tab and snapshot and rejects the rest", () => {
    expect(parsePolicyRuleDetailQuery({ tab: "fires", snapshot: PREVIOUS_SNAPSHOT })).toEqual({
      tab: "fires",
      snapshot: PREVIOUS_SNAPSHOT,
    })
    expect(parsePolicyRuleDetailQuery({ tab: "nope", snapshot: "pol_1999" })).toEqual({
      tab: "overview",
      snapshot: CURRENT_SNAPSHOT,
    })
  })
})

describe("live surface tabs", () => {
  it("keeps only a known Overview tab and keeps the default href clean", () => {
    expect(parseOverviewQuery({ tab: "runs" })).toEqual({ tab: "runs" })
    expect(parseOverviewQuery({ tab: "secrets" })).toEqual(OVERVIEW_DEFAULT)
    expect(serializeOverviewQuery(parseOverviewQuery({ tab: "attention" })).toString()).toBe("")
    expect(overviewHref(OVERVIEW_DEFAULT)).toBe("/")
    expect(overviewHref({ tab: "sources" })).toBe("/?tab=sources")
  })

  it("keeps only a known Platform tab and round-trips it", () => {
    expect(parsePlatformQuery({ tab: "recovery" })).toEqual({ tab: "recovery" })
    expect(parsePlatformQuery({ tab: "raw " })).toEqual(PLATFORM_DEFAULT)
    expect(serializePlatformQuery(PLATFORM_DEFAULT).toString()).toBe("")
    expect(platformHref(PLATFORM_DEFAULT)).toBe("/platform")
    expect(platformHref({ tab: "pipeline" })).toBe("/platform?tab=pipeline")
  })
})
