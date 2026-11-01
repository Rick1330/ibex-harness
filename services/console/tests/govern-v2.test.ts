import { describe, expect, it } from "vitest"
import {
  POLICY_AREA_ORDER,
  POLICY_DECISION_LABELS,
  POLICY_EFFECT_LABELS,
  filterPolicyRulesV2,
  policyImpact,
  policyImpactSummary,
  policyRulesForSnapshot,
  policySnapshotChangeSummary,
  policyStatusLine,
  type PolicyRuleListFilter,
} from "../app/lib/policy-preview"
import {
  DRIFT_STATE_LABELS,
  driftChange,
  driftSignals,
  driftSuspectedCauses,
  filterDriftSignals,
  type DriftListState,
} from "../app/lib/drift-preview"
import {
  AUDIT_INTEGRITY_PENDING,
  DEFAULT_AUDIT_FILTER,
  auditAttentionCounts,
  auditDayLabel,
  auditDiffChangedCount,
  auditDiffChangedKeys,
  auditEvents,
  auditExportBoundary,
  auditExportHistory,
  auditIdempotencyAnswer,
  auditIntegrity,
  auditObjectEvents,
  auditObjectSummary,
  auditPage,
  auditRelated,
  auditStatusLine,
  filterAuditEvents,
  groupAuditEvents,
  parseAuditQuery,
  type AuditListFilter,
} from "../app/lib/audit-preview"
import {
  AUDIT_INTEGRITY_DEFAULT,
  DRIFT_LIST_DEFAULT,
  POLICY_COMPARE_DEFAULT,
  auditEventHref,
  auditIntegrityHref,
  auditListHref,
  auditObjectHistoryHref,
  driftListHref,
  parseAuditEventDetailQuery,
  parseAuditIntegrityQuery,
  parseAuditListQuery,
  parseAuditObjectQuery,
  parseDriftListQuery,
  parsePolicyCompareQuery,
  parsePolicyListQueryV2,
  parsePolicyResolveQuery,
  parsePolicyRuleDetailQueryV2,
  parsePolicySnapshotDetailQuery,
  policyCompareHref,
  policyListHrefV2,
  policyResolveHref,
  serializeAuditEventDetailQuery,
  serializeAuditIntegrityQuery,
  serializeAuditListQuery,
  serializeAuditObjectQuery,
  serializeDriftListQuery,
  serializePolicyCompareQuery,
  serializePolicyListQueryV2,
  serializePolicyResolveQuery,
  serializePolicyRuleDetailQueryV2,
  serializePolicySnapshotDetailQuery,
} from "../app/lib/govern-query"
import { policySnapshots } from "../app/lib/policy-preview"

const CURRENT_SNAPSHOT = policySnapshots[0]!.id
const PREVIOUS_SNAPSHOT = policySnapshots[1]!.id

function asRecord(query: URLSearchParams): Record<string, unknown> {
  return Object.fromEntries(query.entries())
}

describe("policies v2 data", () => {
  it("writes the status line from the snapshot counts and provenance", () => {
    const status = policyStatusLine()
    expect(status.text).toContain("6 rules in force (5 enforced, 1 advisory)")
    expect(status.text).toContain(`from snapshot ${CURRENT_SNAPSHOT}`)
    expect(status.caveat).toContain("4 of 7 linked runs")
    expect(status.caveatDetail).toContain("not that the rule was skipped")
  })

  it("keeps simulation share and transitions in agreement", () => {
    const impact = policyImpact()
    expect(impact.replayed).toBe(1_204)
    expect(impact.changed).toBe(14)
    expect(Number(((impact.changed / impact.replayed) * 100).toFixed(1))).toBe(1.2)
    expect(impact.transitions.reduce((sum, transition) => sum + transition.count, 0)).toBe(14)
    expect(policyImpactSummary(impact)).toBe("1,204 decisions replayed · 14 would change")
  })

  it("filters to the two rules changed in the snapshot", () => {
    const filter: PolicyRuleListFilter = {
      q: "",
      effect: "all",
      mode: "all",
      area: "all",
      changed: true,
    }
    expect(
      filterPolicyRulesV2(policyRulesForSnapshot(CURRENT_SNAPSHOT), filter)
        .map((rule) => rule.label)
        .sort(),
    ).toEqual(["Provider model allowlist", "Refund approval threshold"])
  })

  it("labels metadata-only snapshots instead of claiming no changes", () => {
    const summary = policySnapshotChangeSummary("pol_2026_10_24_01")
    expect(summary.metadataOnly).toBe(true)
    expect(summary.reason).toContain("Metadata only")
    expect(summary.changed).toBe(0)
  })

  it("uses one decision vocabulary and one effect vocabulary", () => {
    const decisions = Object.values(POLICY_DECISION_LABELS)
    expect(decisions).toContain("Asked a person")
    expect(decisions).toContain("Hidden")
    expect(decisions).not.toContain("Approval")
    expect(decisions).not.toContain("Redacted")
    expect(Object.values(POLICY_EFFECT_LABELS)).toContain("Blocks")
    expect(POLICY_AREA_ORDER).toContain("Models")
  })
})

describe("drift data", () => {
  const listState: DriftListState = { ...DRIFT_LIST_DEFAULT, state: "open" }

  it("never shows a resolved signal under the Open filter", () => {
    const open = filterDriftSignals(driftSignals, listState)
    expect(open.map((signal) => signal.id)).toEqual(["sig_tool_calls"])
    expect(open.every((signal) => signal.state === "open")).toBe(true)
    expect(filterDriftSignals(driftSignals, { ...DRIFT_LIST_DEFAULT, state: "all" }).map((signal) => signal.id)).toContain(
      "sig_latency_shift",
    )
  })

  it("renders ratios at or above 2 as a multiplier", () => {
    const toolCalls = driftSignals.find((signal) => signal.id === "sig_tool_calls")!
    expect(driftChange(toolCalls).label).toBe("2.3×")
    expect(driftSignals.length).toBeGreaterThanOrEqual(3)
    expect(Object.values(DRIFT_STATE_LABELS)).toContain("Acknowledged")
  })

  it("ranks a promotion before first sight as a suspected cause", () => {
    const toolCalls = driftSignals.find((signal) => signal.id === "sig_tool_calls")!
    const causes = driftSuspectedCauses(toolCalls)
    expect(causes[0]?.cause.id).toBe("cause_support_v14")
    expect(causes[0]?.cause.at).toBe("2026-10-20T09:00:00Z")
    expect(Date.parse(causes[0]!.cause.at)).toBeLessThan(Date.parse(toolCalls.firstSeen))
    expect(causes[0]?.label).toContain("before")
  })

  it("round-trips the drift filter through the URL", () => {
    const state: DriftListState = {
      q: "tool",
      state: "acknowledged",
      severity: "warning",
      owner: "Priya Nair",
      agent: "ag_support_triage",
      sort: "change",
      cause: "recent",
    }
    expect(parseDriftListQuery(asRecord(serializeDriftListQuery(state)))).toEqual(state)
    expect(driftListHref(DRIFT_LIST_DEFAULT)).toBe("/drift")
    expect(parseDriftListQuery({ state: "bogus", severity: "severe", sort: "bogus" })).toMatchObject({
      state: "active",
      severity: "all",
      sort: "severity",
    })
  })
})

describe("audit data", () => {
  it("never returns rejected or retrying rows from the Applied filter", () => {
    const filter: AuditListFilter = { ...DEFAULT_AUDIT_FILTER, result: "applied" }
    const applied = filterAuditEvents(auditEvents, filter)
    expect(applied.length).toBeGreaterThan(0)
    expect(applied.every((event) => event.result === "applied")).toBe(true)
  })

  it("groups the 14:12:08 promotion under 30 Oct", () => {
    const groups = groupAuditEvents(auditEvents)
    expect(groups[0]?.key).toBe("2026-10-30")
    expect(groups[0]?.label).toBe(auditDayLabel("2026-10-30"))
    expect(groups[0]?.label).toContain("Today")
    expect(groups[0]?.events.some((event) => event.id === "evt_7f3a21" && event.at.startsWith("2026-10-30T14:12:08"))).toBe(
      true,
    )
    expect(groups.find((group) => group.key === "2026-10-29")?.label).toContain("Yesterday")
  })

  it("counts the needs-attention shortcuts without claiming a verified chain", () => {
    const counts = auditAttentionCounts()
    expect(counts).toMatchObject({ retrying: 2, deadLettered: 1, rejected: 4, privileged: 6 })
    expect(counts.chainGaps).toBeNull()
    expect(auditIntegrity).toBeNull()
    expect(AUDIT_INTEGRITY_PENDING).toBe("Integrity checks aren't connected. No verification claim is made.")
    expect(auditStatusLine().text).toBe(
      "Sample events. The audit stream isn't connected, so integrity can't be checked yet.",
    )
  })

  it("puts the dead-lettered event in Needs attention", () => {
    const attention = filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, view: "attention" })
    expect(attention.map((event) => event.id)).toContain("evt_90bd14")
    expect(attention.every((event) => event.result === "retrying" || event.result === "dead_lettered")).toBe(true)
  })

  it("shows two changed keys for the promotion and hides the unchanged actor", () => {
    const promotion = auditEvents.find((event) => event.id === "evt_7f3a21")!
    expect(promotion.diff).toBeDefined()
    expect(auditDiffChangedCount(promotion.diff!)).toBe(2)
    expect(auditDiffChangedKeys(promotion.diff!).map((entry) => entry.key)).toEqual(["state", "live_version"])
    expect(auditDiffChangedKeys(promotion.diff!).map((entry) => entry.key)).not.toContain("actor")
    expect(auditIdempotencyAnswer(promotion)).toMatchObject({ label: "Applied exactly once", effects: 1, duplicates: 0 })
  })

  it("parses the documented query syntax", () => {
    expect(parseAuditQuery('actor:"Jon Park"').actor).toBe("Jon Park")
    expect(parseAuditQuery("action:directive.*").action).toBe("directive.*")
    expect(parseAuditQuery("target:support-v13").target).toBe("support-v13")
    expect(parseAuditQuery("result:dead-lettered").result).toBe("dead_lettered")
    expect(parseAuditQuery("origin:policy").origin).toBe("policy")
    expect(parseAuditQuery("step_up:true").stepUp).toBe(true)
    expect(parseAuditQuery("step_up:maybe").stepUp).toBeNull()
    expect(parseAuditQuery("refund approval").text).toBe("refund approval")

    expect(filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, query: "actor:jon" }).length).toBe(5)
    expect(
      filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, query: "action:directive.*" }).map((event) => event.id),
    ).toEqual(["evt_7f3a21", "evt_d3917c", "evt_508fb4"])
    expect(filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, query: "target:support-v13" })[0]?.id).toBe(
      "evt_7f3a21",
    )
    expect(filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, query: "origin:policy" }).length).toBe(4)
    expect(filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, query: "step_up:true" }).length).toBe(6)
    expect(filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, view: "deletion" }).length).toBe(3)
    expect(filterAuditEvents(auditEvents, { ...DEFAULT_AUDIT_FILTER, view: "mine" }).length).toBe(5)
  })

  it("relates retries and builds object history", () => {
    const deadLetter = auditEvents.find((event) => event.id === "evt_90bd14")!
    expect(auditRelated(deadLetter).map((event) => event.id)).toContain("evt_b16f5a")
    const history = auditObjectEvents("directive", "dir_support_triage", true)
    expect(history.map((event) => event.id)).toEqual(["evt_7f3a21", "evt_d3917c"])
    expect(auditObjectEvents("directive", "dir_support_triage").map((event) => event.id)).toEqual([
      "evt_7f3a21",
      "evt_d3917c",
    ])
    const summary = auditObjectSummary("directive", "dir_support_triage")
    expect(summary).toMatchObject({ count: 2, applied: 2, failed: 0 })
    expect(summary.actors.sort()).toEqual(["Jon Park", "Mira Chen"])
  })

  it("pages the log and states the export boundary", () => {
    const first = auditPage(auditEvents)
    expect(first.items).toHaveLength(12)
    expect(first.hasMore).toBe(true)
    expect(first.nextCursor).toBe("24")
    const full = auditPage(auditEvents, Number(first.nextCursor))
    expect(full.items).toHaveLength(24)
    expect(full.hasMore).toBe(false)
    expect(auditPage(auditEvents, 500).items).toHaveLength(24)

    const boundary = auditExportBoundary()
    expect(boundary.count).toBe(24)
    expect(boundary.text).toContain("24 events")
    expect(auditExportHistory).toHaveLength(0)
  })
})

describe("govern v2 query round-trips", () => {
  it("round-trips the policies list tab and filters", () => {
    const state = parsePolicyListQueryV2({
      tab: "decisions",
      snapshot: PREVIOUS_SNAPSHOT,
      q: "refund",
      effect: "deny",
      mode: "enforced",
      area: "Tools",
      changed: "1",
      sort: "name",
      decision: "blocked",
      range: "30d",
    })
    expect(parsePolicyListQueryV2(asRecord(serializePolicyListQueryV2(state)))).toEqual(state)
    expect(policyListHrefV2(state)).toContain("tab=decisions")
    expect(parsePolicyListQueryV2({ tab: "bogus", area: "Billing", sort: "bogus", decision: "bogus" })).toMatchObject({
      tab: "rules",
      area: "all",
      sort: "severity",
      decision: "all",
    })
  })

  it("round-trips snapshot, compare, rule, and resolve states", () => {
    const snapshotTab = parsePolicySnapshotDetailQuery({ tab: "impact" })
    expect(parsePolicySnapshotDetailQuery(asRecord(serializePolicySnapshotDetailQuery(snapshotTab)))).toEqual(snapshotTab)

    const compare = parsePolicyCompareQuery({ from: CURRENT_SNAPSHOT, to: PREVIOUS_SNAPSHOT, hideUnchanged: "1" })
    expect(parsePolicyCompareQuery(asRecord(serializePolicyCompareQuery(compare)))).toEqual(compare)
    expect(policyCompareHref(POLICY_COMPARE_DEFAULT)).toBe("/policies/compare")
    expect(policyCompareHref(compare)).toContain("from=")

    const rule = parsePolicyRuleDetailQueryV2({ tab: "history", snapshot: PREVIOUS_SNAPSHOT, rev: "4" })
    expect(parsePolicyRuleDetailQueryV2(asRecord(serializePolicyRuleDetailQueryV2(rule)))).toEqual(rule)
    expect(parsePolicyRuleDetailQueryV2({ rev: "-2" }).rev).toBeNull()
    expect(parsePolicyRuleDetailQueryV2({ rev: "9999" }).rev).toBeNull()

    const run = parsePolicyResolveQuery({ run: "run_77b031" })
    expect(parsePolicyResolveQuery(asRecord(serializePolicyResolveQuery(run)))).toEqual(run)
    const at = parsePolicyResolveQuery({ at: "2026-10-25T12:00Z" })
    expect(at).toEqual({ run: "", at: "2026-10-25T12:00Z" })
    expect(parsePolicyResolveQuery({ run: "../etc", at: "not-a-date" })).toEqual({ run: "", at: "" })
    expect(policyResolveHref(run)).toBe("/policies/resolve?run=run_77b031")
  })

  it("round-trips audit filters, tabs, object history, and export state", () => {
    const state = parseAuditListQuery({
      q: 'actor:"Jon Park"',
      view: "privileged",
      result: "rejected",
      origin: "policy",
      range: "24h",
      cursor: "24",
    })
    expect(parseAuditListQuery(asRecord(serializeAuditListQuery(state)))).toEqual(state)
    expect(auditListHref({ ...state, query: "", view: "all", result: "all", origin: "all", range: "7d", cursor: null })).toBe(
      "/audit",
    )
    expect(parseAuditListQuery({ view: "bogus", result: "bogus", origin: "bogus", range: "bogus", cursor: "-4" })).toMatchObject(
      { view: "all", result: "all", origin: "all", range: "7d", cursor: null },
    )

    const eventTab = parseAuditEventDetailQuery({ tab: "related" })
    expect(parseAuditEventDetailQuery(asRecord(serializeAuditEventDetailQuery(eventTab)))).toEqual(eventTab)
    expect(auditEventHref("evt_7f3a21")).toBe("/audit/events/evt_7f3a21")

    const objectState = parseAuditObjectQuery({ actor: "Mira Chen", action: "directive.", failed: "1" })
    expect(parseAuditObjectQuery(asRecord(serializeAuditObjectQuery(objectState)))).toEqual(objectState)
    expect(auditObjectHistoryHref("directive", "dir_support_triage")).toBe(
      "/audit/objects/directive/dir_support_triage",
    )

    const integrity = parseAuditIntegrityQuery({ range: "30d", format: "CSV" })
    expect(integrity).toEqual({ range: "7d", format: "CSV" })
    expect(parseAuditIntegrityQuery(asRecord(serializeAuditIntegrityQuery(integrity)))).toEqual(integrity)
    expect(serializeAuditIntegrityQuery(AUDIT_INTEGRITY_DEFAULT).toString()).toBe("")
    expect(auditIntegrityHref(AUDIT_INTEGRITY_DEFAULT)).toBe("/audit/integrity")
  })
})
