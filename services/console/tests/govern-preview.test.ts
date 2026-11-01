import { describe, expect, it } from "vitest"
import {
  directiveApprovalState,
  directiveAttentionItems,
  directiveBanner,
  directiveById,
  directiveCheckSummary,
  directiveDiff,
  directiveListStats,
  directiveLive,
  directiveRollbackTarget,
  directiveVersion,
  directives,
  filterDirectives,
  sortDirectives,
} from "../app/lib/directive-preview"
import {
  filterPolicyRules,
  POLICY_EFFECT_LABELS,
  policyImpact,
  policyModeCounts,
  policyRawSnapshot,
  policyRecentChanges,
  policyRuleAt,
  policyRuleById,
  policyRuleHref,
  policyRules,
  policyRulesForSnapshot,
  policyRunDecisions,
  policySnapshotAt,
  policySnapshotDiff,
  policySnapshotForRun,
  policySnapshots,
} from "../app/lib/policy-preview"

const CURRENT_SNAPSHOT = policySnapshots[0]!.id
const PREVIOUS_SNAPSHOT = policySnapshots[1]!.id

describe("directive fixtures", () => {
  it("keeps every event id unique per directive", () => {
    for (const directive of directives) {
      const events = directive.events.map((event) => event.id)
      expect(new Set(events).size).toBe(events.length)
      const versionEvents = directive.versions.map((version) => version.eventId)
      expect(new Set(versionEvents).size).toBe(versionEvents.length)
    }
  })

  it("never lets an author approve their own directive", () => {
    const directive = directiveById("dir_support_triage")!
    const candidate = directiveVersion(directive, "v14")!
    expect(candidate.author).toBe("Mira Chen")
    const approval = directiveApprovalState(candidate)
    expect(approval.eligible).toEqual(["Jon Park", "Priya Nair"])
    expect(approval.authorExcluded).toBe(true)
    expect(approval.waiting).toBe(1)
    expect(approval.state).toBe("waiting")
    expect(directiveApprovalState(directiveVersion(directive, "v13")!).state).toBe("approved")
  })

  it("computes the rollback target from the version that was live before the current live version", () => {
    const directive = directiveById("dir_support_triage")!
    expect(directiveLive(directive)?.version).toBe("v13")
    expect(directiveRollbackTarget(directive)?.version).toBe("v12")
    expect(directiveRollbackTarget(directiveById("dir_onboarding_guide")!)).toBeNull()
  })

  it("summarises checks and the blocking banner without counting skipped work as passed", () => {
    const support = directiveVersion(directiveById("dir_support_triage")!, "v14")!
    expect(directiveCheckSummary(support)).toMatchObject({
      total: 4,
      passed: 3,
      pending: 1,
      failed: 0,
      label: "3/4 passed",
      tone: "warning",
    })

    const billing = directiveById("dir_billing_assistant")!
    const summary = directiveCheckSummary(directiveVersion(billing, "v9")!)
    expect(summary).toMatchObject({ total: 4, passed: 2, failed: 1, skipped: 1, label: "2/4 passed", tone: "destructive" })
    expect(directiveBanner(billing)?.tone).toBe("critical")
    expect(directiveBanner(billing)?.text).toContain("cannot be promoted")

    expect(directiveBanner(directiveById("dir_support_triage")!)?.tone).toBe("warning")
    expect(directiveBanner(directiveById("dir_support_triage")!)?.text).toContain("someone else must approve")
  })

  it("diffs live against candidate instead of the full version range", () => {
    const directive = directiveById("dir_support_triage")!
    const diff = directiveDiff(directive, "v13", "v14")
    expect(diff.summary).toMatchObject({ sectionsChanged: 2, sectionsTotal: 4, added: 2, removed: 2 })
    expect(diff.sections.find((section) => section.id === "constraints")?.lines.some((line) => line.type === "removed")).toBe(true)
    expect(diff.sections.find((section) => section.id === "identity")?.changed).toBe(false)
  })

  it("derives list stats and attention items from one source", () => {
    expect(directiveListStats()).toEqual({
      awaiting: 1,
      oldestWaiting: "2026-10-27T14:12:00Z",
      changedLast7Days: 1,
      rollbacksLast30Days: 1,
      failingChecks: 1,
    })
    const attention = directiveAttentionItems()
    expect(attention.map((item) => item.severity)).toEqual(["critical", "warning", "info"])
    expect(attention[0]?.directiveName).toBe("Billing assistant")
    expect(attention[1]?.directiveName).toBe("Support triage")
    expect(attention[2]?.title).toBe("No rollback target")
  })

  it("filters and sorts without mutating the fixture order", () => {
    expect(filterDirectives(directives, { search: "", agent: "all", state: "candidate" })).toHaveLength(2)
    expect(filterDirectives(directives, { search: "", agent: "ag_escalation_router", state: "all" }).map((entry) => entry.id)).toEqual([
      "dir_support_triage",
      "dir_incident_responder",
    ])
    expect(sortDirectives(directives, "name").map((entry) => entry.name)).toEqual([
      "Billing assistant",
      "Incident responder",
      "Onboarding guide",
      "Support triage",
    ])
  })
})

describe("policy fixtures", () => {
  it("orders snapshots newest first and links every snapshot to its predecessor", () => {
    for (let index = 0; index < policySnapshots.length - 1; index += 1) {
      expect(policySnapshots[index]!.previousId).toBe(policySnapshots[index + 1]!.id)
      expect(policySnapshots[index]!.previousDigest).toBe(policySnapshots[index + 1]!.digest)
    }
    expect(policySnapshots.at(-1)!.previousId).toBeNull()
  })

  it("resolves the rule revision that was in force for a snapshot", () => {
    expect(policyRuleAt("data.retention", CURRENT_SNAPSHOT)?.revision).toBe(7)
    expect(policyRuleAt("data.retention", "pol_2026_10_11_01")?.revision).toBe(6)
    expect(policyRuleAt("tools.approval", PREVIOUS_SNAPSHOT)?.revision).toBe(4)
    expect(policyRuleAt("unknown.rule", CURRENT_SNAPSHOT)).toBeNull()
    expect(policyRulesForSnapshot(CURRENT_SNAPSHOT)).toHaveLength(6)
  })

  it("counts enforced and advisory rules from the snapshot, not the current rule list", () => {
    expect(policyModeCounts(CURRENT_SNAPSHOT)).toEqual({ enforced: 5, advisory: 1 })
    expect(policyRulesForSnapshot(CURRENT_SNAPSHOT).find((rule) => rule.revision.mode === "advisory")?.id).toBe("content.pii")
    expect(POLICY_EFFECT_LABELS.wrap_as_data).toBe("Treats as data")
  })

  it("keeps snapshot diffs to the changed rules", () => {
    const diff = policySnapshotDiff(CURRENT_SNAPSHOT)
    expect(diff.changed.map((rule) => rule.id).sort()).toEqual(["models.allowlist", "tools.approval"])
    expect(diff.unchanged).toBe(4)
    expect(diff.added).toBe(0)
    expect(diff.removed).toBe(0)
  })

  it("reports recent changes across the snapshot span with their revision pair", () => {
    const changes = policyRecentChanges(3)
    expect(changes).toHaveLength(3)
    expect(changes.map((change) => change.ruleId).sort()).toEqual(["data.retention", "models.allowlist", "tools.approval"])
    const retention = changes.find((change) => change.ruleId === "data.retention")!
    expect(retention.fromRevision).toBe(6)
    expect(retention.toRevision).toBe(7)
    expect(retention.at).toBe("2026-10-18T03:00:00Z")
  })

  it("adds revised decisions up to the replayed total", () => {
    const impact = policyImpact()
    expect(impact).toMatchObject({ status: "passed", replayed: 1204, changed: 14, unchanged: 1190 })
    expect(impact.transitions.reduce((sum, transition) => sum + transition.count, 0)).toBe(impact.changed)
    expect(impact.byRule.map((rule) => rule.ruleId).sort()).toEqual(["models.allowlist", "tools.approval"])
  })

  it("keeps revision event ids unique and never reuses the publication event", () => {
    const ids = policyRules.flatMap((rule) => rule.revisions.map((revision) => revision.eventId))
    expect(new Set(ids).size).toBe(ids.length)
    expect(ids).not.toContain("evt_5b2c90")
  })

  it("resolves time travel from an instant and from a linked run", () => {
    expect(policySnapshotAt("2026-10-25T00:00:00Z")?.id).toBe(PREVIOUS_SNAPSHOT)
    expect(policySnapshotAt("2026-10-10T00:00:00Z")).toBeNull()
    expect(policySnapshotForRun("run_8ad1c0")?.id).toBe(PREVIOUS_SNAPSHOT)
    expect(policySnapshotForRun("run_unknown")).toBeNull()
    expect(policyRunDecisions.every((decision) => decision.ruleId !== "")).toBe(true)
  })

  it("exposes a raw snapshot view with one row per rule", () => {
    const rows = policyRawSnapshot(CURRENT_SNAPSHOT)
    expect(rows).toHaveLength(6)
    expect(new Set(rows.map((row) => row.ruleId)).size).toBe(rows.length)
    expect(rows.every((row) => row.condition.length > 0)).toBe(true)
  })

  it("filters by effect, mode, scope, and text", () => {
    const rules = policyRulesForSnapshot(CURRENT_SNAPSHOT)
    const filter = { q: "", effect: "all" as const, mode: "all" as const, scope: "all" }
    expect(filterPolicyRules(rules, { ...filter, mode: "advisory" }).map((rule) => rule.id)).toEqual(["content.pii"])
    expect(filterPolicyRules(rules, { ...filter, effect: "deny" }).map((rule) => rule.id)).toEqual(["budget.ceiling", "models.allowlist"])
    expect(filterPolicyRules(rules, { ...filter, q: "refund" }).map((rule) => rule.id)).toEqual(["tools.approval"])
    expect(filterPolicyRules(rules, { ...filter, scope: "org_demo_42 · providers" }).map((rule) => rule.id)).toEqual(["models.allowlist"])
  })

  it("builds rule links that preserve a non-current snapshot", () => {
    expect(policyRuleHref("tools.approval")).toBe("/policies/rules/tools.approval")
    expect(policyRuleHref("tools.approval", PREVIOUS_SNAPSHOT)).toBe(`/policies/rules/tools.approval?snapshot=${PREVIOUS_SNAPSHOT}`)
    expect(policyRuleById("missing.rule")).toBeNull()
  })
})
