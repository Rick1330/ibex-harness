import { formatGovernNumber } from "./govern-format"
import { diffDirectiveSections, type SectionDiff } from "./govern-diff"

export type PolicyEffect = "deny" | "require_approval" | "redact" | "wrap_as_data" | "tombstone" | "allow"
export type PolicyMode = "enforced" | "advisory"
export type PolicyArea = "Spend" | "Data" | "Context" | "Tools" | "Models" | "Content"
export type PolicyRuleTab = "overview" | "fires" | "history" | "scope"
export type PolicyEffectFilter = PolicyEffect | "all"
export type PolicyModeFilter = PolicyMode | "all"

export const POLICY_RULE_TABS: { id: PolicyRuleTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "fires", label: "Fires" },
  { id: "history", label: "History" },
  { id: "scope", label: "Where it applies" },
]

export const POLICY_AREA_ORDER: PolicyArea[] = ["Spend", "Data", "Context", "Tools", "Models", "Content"]

/** Blocks first: the sort order an operator triages by. */
export const POLICY_EFFECT_ORDER: Record<PolicyEffect, number> = {
  deny: 0,
  require_approval: 1,
  redact: 2,
  wrap_as_data: 3,
  tombstone: 4,
  allow: 5,
}

export const POLICY_EFFECT_LABELS: Record<PolicyEffect, string> = {
  deny: "Blocks",
  require_approval: "Asks a person",
  redact: "Hides",
  wrap_as_data: "Treats as data",
  tombstone: "Deletes after window",
  allow: "Allows",
}

export const POLICY_EFFECT_DESCRIPTIONS: Record<PolicyEffect, string> = {
  deny: "Stops the action before the tool runs.",
  require_approval: "Pauses the action until an operator approves it.",
  redact: "Removes the matched content from the model input or output.",
  wrap_as_data: "Delimits untrusted content so it is treated as data, never as instructions.",
  tombstone: "Marks the record deleted and removes its content after the retention window.",
  allow: "Permits the action without further checks.",
}

export const POLICY_MODE_LABELS: Record<PolicyMode, string> = {
  enforced: "Enforced",
  advisory: "Advisory",
}

export const POLICY_MODE_DESCRIPTIONS: Record<PolicyMode, string> = {
  enforced: "The decision is applied to the run.",
  advisory: "The decision is recorded as a warning and the run continues.",
}

/** One vocabulary for rule effects and run decisions (brief §0). */
export const POLICY_DECISION_LABELS: Record<PolicyDecisionKind, string> = {
  allowed: "Allowed",
  blocked: "Blocked",
  approval: "Asked a person",
  redacted: "Hidden",
  wrapped: "Wrapped",
  tombstoned: "Deleted",
}

export const POLICY_DECISION_ORDER: PolicyDecisionKind[] = [
  "blocked",
  "approval",
  "redacted",
  "wrapped",
  "tombstoned",
  "allowed",
]

export const POLICY_EFFECT_FILTER_LABELS: Record<PolicyEffectFilter, string> = {
  all: "All effects",
  ...POLICY_EFFECT_LABELS,
}

export const POLICY_MODE_FILTER_LABELS: Record<PolicyModeFilter, string> = {
  all: "All modes",
  ...POLICY_MODE_LABELS,
}

export type PolicySnapshot = {
  id: string
  effectiveFrom: string
  publishedAt: string
  publishedBy: string
  digest: string
  previousDigest: string | null
  previousId: string | null
  message: string
  /** Present when a snapshot exists only to correct release metadata. */
  metadataNote?: string | null
}

export type PolicyTransition = {
  from: PolicyEffect
  to: PolicyEffect
  count: number
}

export type PolicyRevisionImpact = {
  status: "passed" | "failed" | "not_run"
  replayed: number
  changed: number
  transitions: PolicyTransition[]
}

export type PolicyRuleRevision = {
  revision: number
  effect: PolicyEffect
  mode: PolicyMode
  condition: string
  summary: string
  effectiveFrom: string
  changedBy: string
  changeSummary: string
  hash: string
  eventId: string
  snapshotIds: string[]
  impact: PolicyRevisionImpact | null
}

export type PolicyRule = {
  id: string
  label: string
  area: PolicyArea
  scope: string
  owner: string
  revisions: PolicyRuleRevision[]
  fired: number | null
  /** Fires in the seven days before the current window; null when not reported. */
  firedPrev: number | null
  /** Fourteen daily counts, oldest first, ending on the reporting day. */
  firedTrend: number[]
  impacted: number | null
  matches: { agent: string; runs: number }[]
}

export type PolicyDecisionKind = "allowed" | "blocked" | "approval" | "redacted" | "wrapped" | "tombstoned"

export type PolicyApprovalOutcome = {
  state: "granted" | "denied" | "pending"
  by: string | null
  minutes: number | null
}

export type PolicyRunDecision = {
  runId: string
  at: string
  snapshotId: string
  ruleId: string
  ruleRevision: number
  effect: PolicyEffect
  decision: PolicyDecisionKind
  evidence: "certified" | "sampled" | null
  provenance: "complete" | "partial"
  agent: string
  agentVersion: string
  approval?: PolicyApprovalOutcome
  summary: string
}

export type PolicyEventAction = "created" | "revised" | "published" | "retired"

export const POLICY_EVENT_LABELS: Record<PolicyEventAction, string> = {
  created: "Rule created",
  revised: "Rule revised",
  published: "Published in snapshot",
  retired: "Rule retired",
}

export type PolicyEvent = {
  id: string
  action: PolicyEventAction
  actor: string
  at: string
  revision: number | null
  summary: string
}

export type PolicyCheck = {
  id: string
  name: string
  state: "passed" | "failed" | "pending" | "skipped"
  result: string
  at: string | null
}

export type PolicyPublication = {
  eventId: string
  actor: string
  at: string
  idempotencyKey: string
  appliedOnce: boolean
  summary: string
}

const HASH_BASE = "2c81a4e7b9f0d1c3a5e64829b7d3f0a1c2e4b6d8f0a2c4e6b8d0f2a4c6e8b0d2"

function digest(suffix: string): string {
  return `sha256:${HASH_BASE.slice(0, 56)}${suffix}`
}

export const policySnapshots: PolicySnapshot[] = [
  {
    id: "pol_2026_10_27_03",
    effectiveFrom: "2026-10-27T03:00:00Z",
    publishedAt: "2026-10-27T02:47:00Z",
    publishedBy: "Jon Park",
    digest: digest("c81e"),
    previousDigest: digest("77b0"),
    previousId: "pol_2026_10_24_01",
    message: "Tighten refund approval and retire claude-sonnet-4.",
  },
  {
    id: "pol_2026_10_24_01",
    effectiveFrom: "2026-10-24T03:00:00Z",
    publishedAt: "2026-10-24T02:41:00Z",
    publishedBy: "Mira Chen",
    digest: digest("77b0"),
    previousDigest: digest("5b2c"),
    previousId: "pol_2026_10_18_02",
    message: "Promote the context injection wrapper after review.",
    metadataNote: "Metadata only: release note edited; no rule bytes changed.",
  },
  {
    id: "pol_2026_10_18_02",
    effectiveFrom: "2026-10-18T03:00:00Z",
    publishedAt: "2026-10-18T02:38:00Z",
    publishedBy: "Priya Nair",
    digest: digest("5b2c"),
    previousDigest: digest("1a07"),
    previousId: "pol_2026_10_11_01",
    message: "Shorten memory retention to 30 days.",
  },
  {
    id: "pol_2026_10_11_01",
    effectiveFrom: "2026-10-11T03:00:00Z",
    publishedAt: "2026-10-11T02:36:00Z",
    publishedBy: "Jon Park",
    digest: digest("1a07"),
    previousDigest: null,
    previousId: null,
    message: "Add advisory PII redaction and the model allowlist.",
  },
]

const CURRENT_SNAPSHOT = "pol_2026_10_27_03"
const PREVIOUS_SNAPSHOT = "pol_2026_10_24_01"
const SNAPSHOT_IDS = {
  oct27: "pol_2026_10_27_03",
  oct24: "pol_2026_10_24_01",
  oct18: "pol_2026_10_18_02",
  oct11: "pol_2026_10_11_01",
} as const
const ALL_SNAPSHOTS = [SNAPSHOT_IDS.oct11, SNAPSHOT_IDS.oct18, SNAPSHOT_IDS.oct24, SNAPSHOT_IDS.oct27]

const TRANSITIONS_CURRENT: PolicyTransition[] = [
  { from: "allow", to: "require_approval", count: 9 },
  { from: "require_approval", to: "allow", count: 1 },
  { from: "allow", to: "deny", count: 3 },
  { from: "deny", to: "allow", count: 1 },
]

const TRANSITIONS_RETENTION: PolicyTransition[] = [{ from: "allow", to: "tombstone", count: 6 }]

function currentImpact(changed: number, transitions: PolicyTransition[] = []): PolicyRevisionImpact {
  return {
    status: "passed",
    replayed: 1204,
    changed,
    transitions,
  }
}

export const policyRules: PolicyRule[] = [
  {
    id: "budget.ceiling",
    label: "Workspace budget ceiling",
    area: "Spend",
    scope: "org_demo_42 · production",
    owner: "Priya Nair",
    fired: 38,
    firedPrev: 38,
    firedTrend: [5, 5, 6, 5, 6, 5, 6, 5, 6, 5, 5, 6, 5, 6],
    impacted: 0,
    matches: [
      { agent: "Support triage · v14", runs: 21 },
      { agent: "Billing assistant · v9", runs: 17 },
    ],
    revisions: [
      {
        revision: 3,
        effect: "deny",
        mode: "enforced",
        condition: "spend.reserved_total > budget.limit",
        summary: "Blocks a run when its reserved spend would push the workspace past the monthly budget.",
        effectiveFrom: "2026-10-11T03:00:00Z",
        changedBy: "Priya Nair",
        changeSummary: "Reservation check replaced the post-run reconciliation check.",
        hash: digest("b3c4"),
        eventId: "evt_3c4d12",
        snapshotIds: ALL_SNAPSHOTS,
        impact: null,
      },
      {
        revision: 2,
        effect: "require_approval",
        mode: "enforced",
        condition: "spend.month_to_date > budget.limit * 0.9",
        summary: "Asks an operator to approve runs once the workspace reaches 90% of its monthly budget.",
        effectiveFrom: "2026-09-27T03:00:00Z",
        changedBy: "Jon Park",
        changeSummary: "Added an approval step before the hard ceiling.",
        hash: digest("a2b3"),
        eventId: "evt_2b3c01",
        snapshotIds: [],
        impact: null,
      },
      {
        revision: 1,
        effect: "allow",
        mode: "enforced",
        condition: "true",
        summary: "Permits runs and reconciles spend after completion.",
        effectiveFrom: "2026-09-13T03:00:00Z",
        changedBy: "Mira Chen",
        changeSummary: "Initial workspace spend policy.",
        hash: digest("9a1b"),
        eventId: "evt_1a2b90",
        snapshotIds: [],
        impact: null,
      },
    ],
  },
  {
    id: "data.retention",
    label: "Memory retention window",
    area: "Data",
    scope: "org_demo_42 · memories",
    owner: "Priya Nair",
    fired: 214,
    firedPrev: 213,
    firedTrend: [30, 31, 30, 31, 30, 31, 30, 30, 31, 30, 31, 30, 31, 31],
    impacted: 0,
    matches: [
      { agent: "Support triage · v14", runs: 109 },
      { agent: "Incident responder · v5", runs: 105 },
    ],
    revisions: [
      {
        revision: 7,
        effect: "tombstone",
        mode: "enforced",
        condition: "memory.created_at < now() - interval '30 days'",
        summary: "Deletes memory records 30 days after they were written.",
        effectiveFrom: "2026-10-18T03:00:00Z",
        changedBy: "Priya Nair",
        changeSummary: "Reduced the retention window from 45 to 30 days.",
        hash: digest("d4e5"),
        eventId: "evt_4d5e23",
        snapshotIds: [SNAPSHOT_IDS.oct18, SNAPSHOT_IDS.oct24, SNAPSHOT_IDS.oct27],
        impact: currentImpact(0, TRANSITIONS_RETENTION),
      },
      {
        revision: 6,
        effect: "tombstone",
        mode: "enforced",
        condition: "memory.created_at < now() - interval '45 days'",
        summary: "Deletes memory records 45 days after they were written.",
        effectiveFrom: "2026-10-04T03:00:00Z",
        changedBy: "Jon Park",
        changeSummary: "Aligned retention with the workspace data agreement.",
        hash: digest("c3d4"),
        eventId: "evt_4d5e24",
        snapshotIds: [SNAPSHOT_IDS.oct11],
        impact: null,
      },
      {
        revision: 5,
        effect: "tombstone",
        mode: "enforced",
        condition: "memory.created_at < now() - interval '60 days'",
        summary: "Deletes memory records 60 days after they were written.",
        effectiveFrom: "2026-09-20T03:00:00Z",
        changedBy: "Mira Chen",
        changeSummary: "Initial retention rule.",
        hash: digest("b2c3"),
        eventId: "evt_4d5e25",
        snapshotIds: [],
        impact: null,
      },
    ],
  },
  {
    id: "context.injection",
    label: "Untrusted context wrapper",
    area: "Context",
    scope: "org_demo_42 · context",
    owner: "Mira Chen",
    fired: 611,
    firedPrev: 599,
    firedTrend: [84, 85, 86, 85, 86, 87, 86, 87, 88, 87, 88, 87, 88, 86],
    impacted: 0,
    matches: [{ agent: "Support triage · v14", runs: 611 }],
    revisions: [
      {
        revision: 2,
        effect: "wrap_as_data",
        mode: "enforced",
        condition: "source.trust != 'operator'",
        summary: "Wraps retrieved memories in data delimiters so they are never treated as instructions.",
        effectiveFrom: "2026-10-11T03:00:00Z",
        changedBy: "Mira Chen",
        changeSummary: "Wrapper promoted from advisory to enforced after review.",
        hash: digest("e5f6"),
        eventId: "evt_5e6f34",
        snapshotIds: ALL_SNAPSHOTS,
        impact: null,
      },
      {
        revision: 1,
        effect: "wrap_as_data",
        mode: "advisory",
        condition: "source.trust != 'operator'",
        summary: "Records when retrieved memories would have been wrapped, without changing the prompt.",
        effectiveFrom: "2026-09-06T03:00:00Z",
        changedBy: "Jon Park",
        changeSummary: "Initial advisory wrapper for retrieved memories.",
        hash: digest("d4e5"),
        eventId: "evt_5e6f35",
        snapshotIds: [],
        impact: null,
      },
    ],
  },
  {
    id: "tools.approval",
    label: "Refund approval threshold",
    area: "Tools",
    scope: "org_demo_42 · tools",
    owner: "Jon Park",
    fired: 47,
    firedPrev: 42,
    firedTrend: [5, 6, 6, 5, 6, 7, 7, 6, 5, 7, 6, 8, 7, 8],
    impacted: 10,
    matches: [{ agent: "Support triage · v14", runs: 47 }],
    revisions: [
      {
        revision: 5,
        effect: "require_approval",
        mode: "enforced",
        condition: "tool.name == 'refund.issue'",
        summary: "Asks a person to approve every refund before the tool runs.",
        effectiveFrom: "2026-10-27T03:00:00Z",
        changedBy: "Jon Park",
        changeSummary: "Removed the amount threshold so every refund needs approval.",
        hash: digest("f6a7"),
        eventId: "evt_6f7a45",
        snapshotIds: [SNAPSHOT_IDS.oct27],
        impact: currentImpact(10, TRANSITIONS_CURRENT),
      },
      {
        revision: 4,
        effect: "require_approval",
        mode: "enforced",
        condition: "tool.name == 'refund.issue' && tool.amount > 200",
        summary: "Asks a person to approve refunds above $200.",
        effectiveFrom: "2026-10-24T03:00:00Z",
        changedBy: "Priya Nair",
        changeSummary: "Lowered the approval threshold from $250 to $200.",
        hash: digest("a7b8"),
        eventId: "evt_7a8b56",
        snapshotIds: [SNAPSHOT_IDS.oct18, SNAPSHOT_IDS.oct24],
        impact: null,
      },
      {
        revision: 3,
        effect: "require_approval",
        mode: "enforced",
        condition: "tool.name == 'refund.issue' && tool.amount > 250",
        summary: "Asks a person to approve refunds above $250.",
        effectiveFrom: "2026-10-11T03:00:00Z",
        changedBy: "Mira Chen",
        changeSummary: "Initial refund approval threshold.",
        hash: digest("b8c9"),
        eventId: "evt_8b9c67",
        snapshotIds: [SNAPSHOT_IDS.oct11],
        impact: null,
      },
    ],
  },
  {
    id: "models.allowlist",
    label: "Provider model allowlist",
    area: "Models",
    scope: "org_demo_42 · providers",
    owner: "Priya Nair",
    fired: 120,
    firedPrev: 111,
    firedTrend: [15, 16, 16, 15, 16, 17, 16, 17, 18, 16, 17, 18, 17, 17],
    impacted: 4,
    matches: [
      { agent: "Support triage · v14", runs: 64 },
      { agent: "Billing assistant · v9", runs: 31 },
      { agent: "Onboarding guide · v2", runs: 25 },
    ],
    revisions: [
      {
        revision: 4,
        effect: "deny",
        mode: "enforced",
        condition: "model.id not in manifest.approved",
        summary: "Blocks any model that is not in the approved provider manifest.",
        effectiveFrom: "2026-10-27T03:00:00Z",
        changedBy: "Priya Nair",
        changeSummary: "Added gpt-4.1 and removed claude-sonnet-4.",
        hash: digest("c9d0"),
        eventId: "evt_9c0d78",
        snapshotIds: [SNAPSHOT_IDS.oct27],
        impact: currentImpact(4, TRANSITIONS_CURRENT),
      },
      {
        revision: 3,
        effect: "deny",
        mode: "enforced",
        condition: "model.id not in manifest.approved",
        summary: "Blocks any model that is not in the approved provider manifest.",
        effectiveFrom: "2026-10-11T03:00:00Z",
        changedBy: "Mira Chen",
        changeSummary: "Initial provider allowlist with claude-sonnet-4 approved.",
        hash: digest("d0e1"),
        eventId: "evt_0d1e89",
        snapshotIds: [SNAPSHOT_IDS.oct11, SNAPSHOT_IDS.oct18, SNAPSHOT_IDS.oct24],
        impact: null,
      },
      {
        revision: 2,
        effect: "allow",
        mode: "enforced",
        condition: "true",
        summary: "Permits any provider model that reports a known capability manifest.",
        effectiveFrom: "2026-09-06T03:00:00Z",
        changedBy: "Jon Park",
        changeSummary: "Initial provider model policy.",
        hash: digest("e1f2"),
        eventId: "evt_1e2f90",
        snapshotIds: [],
        impact: null,
      },
    ],
  },
  {
    id: "content.pii",
    label: "Personal data redaction",
    area: "Content",
    scope: "org_demo_42 · content",
    owner: "Mira Chen",
    fired: 174,
    firedPrev: 170,
    firedTrend: [22, 25, 24, 25, 24, 25, 25, 25, 24, 25, 25, 24, 25, 26],
    impacted: 0,
    matches: [
      { agent: "Support triage · v14", runs: 98 },
      { agent: "Incident responder · v5", runs: 76 },
    ],
    revisions: [
      {
        revision: 2,
        effect: "redact",
        mode: "advisory",
        condition: "pii.detected",
        summary: "Marks personal data for redaction; advisory, so the run records a warning instead of blocking.",
        effectiveFrom: "2026-10-11T03:00:00Z",
        changedBy: "Priya Nair",
        changeSummary: "Detector narrowed to email, phone, and government ids.",
        hash: digest("f2a3"),
        eventId: "evt_2f3a01",
        snapshotIds: ALL_SNAPSHOTS,
        impact: null,
      },
      {
        revision: 1,
        effect: "redact",
        mode: "advisory",
        condition: "pii.detected",
        summary: "Records personal data detected in prompts and completions.",
        effectiveFrom: "2026-09-06T03:00:00Z",
        changedBy: "Mira Chen",
        changeSummary: "Initial advisory PII detector.",
        hash: digest("a3b4"),
        eventId: "evt_3a4b12",
        snapshotIds: [],
        impact: null,
      },
    ],
  },
]

export const policyRunDecisions: PolicyRunDecision[] = [
  {
    runId: "run_77b031",
    at: "2026-10-30T10:04:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "budget.ceiling",
    ruleRevision: 3,
    effect: "allow",
    decision: "allowed",
    evidence: "certified",
    provenance: "complete",
    agent: "Support triage",
    agentVersion: "v14",
    summary: "Reserved spend stayed under the workspace ceiling.",
  },
  {
    runId: "run_9ac3d2",
    at: "2026-10-29T16:38:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "budget.ceiling",
    ruleRevision: 3,
    effect: "deny",
    decision: "blocked",
    evidence: "certified",
    provenance: "complete",
    agent: "Billing assistant",
    agentVersion: "v9",
    summary: "The run would have pushed the workspace past its monthly budget.",
  },
  {
    runId: "run_1f0b84",
    at: "2026-10-28T09:12:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "context.injection",
    ruleRevision: 2,
    effect: "wrap_as_data",
    decision: "wrapped",
    evidence: "sampled",
    provenance: "partial",
    agent: "Support triage",
    agentVersion: "v14",
    summary: "Retrieved memories were wrapped as data before prompt assembly.",
  },
  {
    runId: "run_2c81a4",
    at: "2026-10-29T11:47:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "tools.approval",
    ruleRevision: 5,
    effect: "require_approval",
    decision: "approval",
    evidence: "certified",
    provenance: "partial",
    agent: "Support triage",
    agentVersion: "v14",
    approval: { state: "pending", by: null, minutes: null },
    summary: "A $140 refund paused for approval under the tightened threshold.",
  },
  {
    runId: "run_5e92fb",
    at: "2026-10-27T18:21:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "tools.approval",
    ruleRevision: 5,
    effect: "require_approval",
    decision: "approval",
    evidence: "sampled",
    provenance: "partial",
    agent: "Support triage",
    agentVersion: "v14",
    approval: { state: "granted", by: "Jon Park", minutes: 6 },
    summary: "A $310 refund paused for approval and was approved by Jon Park.",
  },
  {
    runId: "run_8ad1c0",
    at: "2026-10-25T14:06:00Z",
    snapshotId: "pol_2026_10_24_01",
    ruleId: "tools.approval",
    ruleRevision: 4,
    effect: "require_approval",
    decision: "approval",
    evidence: "certified",
    provenance: "complete",
    agent: "Billing assistant",
    agentVersion: "v9",
    approval: { state: "granted", by: "Priya Nair", minutes: 18 },
    summary: "A $240 refund paused for approval under the $200 threshold.",
  },
  {
    runId: "run_4d10a3",
    at: "2026-10-30T08:53:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "content.pii",
    ruleRevision: 2,
    effect: "redact",
    decision: "redacted",
    evidence: "sampled",
    provenance: "partial",
    agent: "Incident responder",
    agentVersion: "v5",
    summary: "An advisory PII warning was recorded; the run continued.",
  },
  {
    runId: "run_c1d2e3",
    at: "2026-10-28T22:14:00Z",
    snapshotId: CURRENT_SNAPSHOT,
    ruleId: "models.allowlist",
    ruleRevision: 4,
    effect: "deny",
    decision: "blocked",
    evidence: "certified",
    provenance: "complete",
    agent: "Onboarding guide",
    agentVersion: "v2",
    summary: "claude-sonnet-4 is no longer approved; the run was blocked.",
  },
  {
    runId: "run_f4a5b6",
    at: "2026-10-20T07:41:00Z",
    snapshotId: "pol_2026_10_18_02",
    ruleId: "data.retention",
    ruleRevision: 7,
    effect: "tombstone",
    decision: "tombstoned",
    evidence: "certified",
    provenance: "complete",
    agent: "Support triage",
    agentVersion: "v14",
    summary: "Two memories older than 30 days were tombstoned.",
  },
]

export const policyChecks: PolicyCheck[] = [
  {
    id: "schema",
    name: "Schema validation",
    state: "passed",
    result: "6 rules parse against the published operator policy schema.",
    at: "2026-10-27T02:39:00Z",
  },
  {
    id: "simulation",
    name: "Rule simulation",
    state: "passed",
    result: "1,204 prior decisions replayed; 14 would change.",
    at: "2026-10-27T02:44:00Z",
  },
  {
    id: "approval",
    name: "Publication approval",
    state: "passed",
    result: "Approved by Priya Nair.",
    at: "2026-10-27T02:45:00Z",
  },
  {
    id: "provenance",
    name: "Run provenance",
    state: "pending",
    result: "2 of 3 linked runs join to certified evidence; one run is sampled only.",
    at: null,
  },
]

export const policyPublication: PolicyPublication = {
  eventId: "evt_5b2c90",
  actor: "Jon Park",
  at: "2026-10-27T02:47:00Z",
  idempotencyKey: "pol-publish-2026-10-27-03",
  appliedOnce: true,
  summary: "Published snapshot pol_2026_10_27_03 with 2 changed rules.",
}

export function policyCurrentSnapshot(): PolicySnapshot {
  return policySnapshots[0]!
}

export function policyPreviousSnapshot(snapshotId: string): PolicySnapshot | null {
  const index = policySnapshots.findIndex((snapshot) => snapshot.id === snapshotId)
  if (index < 0) return null
  return policySnapshots[index + 1] ?? null
}

export function policySnapshotById(snapshotId: string | null | undefined): PolicySnapshot | null {
  if (!snapshotId) return null
  return policySnapshots.find((snapshot) => snapshot.id === snapshotId) ?? null
}

export type PolicyRuleView = PolicyRule & {
  revision: PolicyRuleRevision
  previousRevision: PolicyRuleRevision | null
}

export function policyRuleById(ruleId: string): PolicyRule | null {
  return policyRules.find((rule) => rule.id === ruleId) ?? null
}

export function policyRuleAt(ruleId: string, snapshotId: string): PolicyRuleRevision | null {
  const rule = policyRuleById(ruleId)
  if (!rule) return null
  return rule.revisions.find((revision) => revision.snapshotIds.includes(snapshotId)) ?? null
}

export function policyRulesForSnapshot(snapshotId: string): PolicyRuleView[] {
  const previous = policyPreviousSnapshot(snapshotId)
  const views: PolicyRuleView[] = []
  for (const rule of policyRules) {
    const revision = policyRuleAt(rule.id, snapshotId)
    if (!revision) continue
    const previousRevision = previous ? policyRuleAt(rule.id, previous.id) : null
    views.push({ ...rule, revision, previousRevision })
  }
  return views
}

export type PolicySnapshotDiff = {
  previous: PolicySnapshot | null
  changed: PolicyRuleView[]
  unchanged: number
  added: number
  removed: number
}

export function policySnapshotDiff(snapshotId: string): PolicySnapshotDiff {
  const previous = policyPreviousSnapshot(snapshotId)
  const currentRules = policyRulesForSnapshot(snapshotId)
  const changed = currentRules.filter(
    (rule) => !rule.previousRevision || rule.previousRevision.revision !== rule.revision.revision,
  )
  const currentIds = new Set(currentRules.map((rule) => rule.id))
  const previousRules = previous ? policyRulesForSnapshot(previous.id) : []
  const removed = previousRules.filter((rule) => !currentIds.has(rule.id)).length
  const previousIds = new Set(previousRules.map((rule) => rule.id))
  const added = currentRules.filter((rule) => !previousIds.has(rule.id)).length
  return {
    previous,
    changed,
    unchanged: currentRules.length - changed.length,
    added,
    removed,
  }
}

export type PolicyRecentChange = {
  ruleId: string
  label: string
  fromRevision: number | null
  toRevision: number
  changedBy: string
  at: string
  summary: string
  effect: PolicyEffect
}

/**
 * Compares the newest snapshot with the snapshot `span` positions back, so a
 * three-snapshot span reports every rule change made in between.
 */
export function policyRecentChanges(span = 3): PolicyRecentChange[] {
  const baseline = policySnapshots[Math.min(span, policySnapshots.length - 1)]
  if (!baseline) return []
  const changes: PolicyRecentChange[] = []
  for (const rule of policyRules) {
    const current = policyRuleAt(rule.id, CURRENT_SNAPSHOT)
    const before = policyRuleAt(rule.id, baseline.id)
    if (!current) continue
    if (before && before.revision === current.revision) continue
    changes.push({
      ruleId: rule.id,
      label: rule.label,
      fromRevision: before?.revision ?? null,
      toRevision: current.revision,
      changedBy: current.changedBy,
      at: current.effectiveFrom,
      summary: current.changeSummary,
      effect: current.effect,
    })
  }
  return changes.sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
}

export function policyModeCounts(snapshotId: string): { enforced: number; advisory: number } {
  const counts = { enforced: 0, advisory: 0 }
  for (const rule of policyRulesForSnapshot(snapshotId)) counts[rule.revision.mode] += 1
  return counts
}

export function policyEffectCounts(snapshotId: string): { effect: PolicyEffect; count: number }[] {
  const totals = new Map<PolicyEffect, number>()
  for (const rule of policyRulesForSnapshot(snapshotId)) {
    totals.set(rule.revision.effect, (totals.get(rule.revision.effect) ?? 0) + 1)
  }
  return [...totals.entries()]
    .map(([effect, count]) => ({ effect, count }))
    .sort((left, right) => right.count - left.count || POLICY_EFFECT_LABELS[left.effect].localeCompare(POLICY_EFFECT_LABELS[right.effect]))
}

export type PolicyImpact = {
  status: "passed" | "failed" | "not_run"
  windowFrom: string
  windowTo: string
  replayed: number
  changed: number
  unchanged: number
  transitions: PolicyTransition[]
  byRule: { ruleId: string; label: string; changed: number; fired: number }[]
}

export function policyImpact(snapshotId = CURRENT_SNAPSHOT): PolicyImpact {
  const views = policyRulesForSnapshot(snapshotId)
  const replayed = views.reduce((sum, rule) => sum + (rule.fired ?? 0), 0)
  const changed = views.reduce((sum, rule) => sum + (rule.impacted ?? 0), 0)
  const ruleChanges = views
    .filter((rule) => (rule.impacted ?? 0) > 0)
    .map((rule) => ({ ruleId: rule.id, label: rule.label, changed: rule.impacted ?? 0, fired: rule.fired ?? 0 }))
  const transitions = snapshotId === CURRENT_SNAPSHOT ? TRANSITIONS_CURRENT : []
  return {
    status: "passed",
    windowFrom: "2026-10-04T00:00:00Z",
    windowTo: "2026-10-30T13:12:00Z",
    replayed,
    changed,
    unchanged: replayed - changed,
    transitions,
    byRule: ruleChanges,
  }
}

export function policyRuleRuns(ruleId: string): PolicyRunDecision[] {
  return policyRunDecisions.filter((decision) => decision.ruleId === ruleId)
}

export function policyRuleEvents(rule: PolicyRule): PolicyEvent[] {
  const events: PolicyEvent[] = []
  const snapshotsById = new Map(policySnapshots.map((snapshot) => [snapshot.id, snapshot]))
  for (const revision of rule.revisions) {
    events.push({
      id: revision.eventId,
      action: revision.revision === 1 ? "created" : "revised",
      actor: revision.changedBy,
      at: revision.effectiveFrom,
      revision: revision.revision,
      summary: revision.changeSummary,
    })
    for (const snapshotId of revision.snapshotIds) {
      const snapshot = snapshotsById.get(snapshotId)
      if (!snapshot) continue
      events.push({
        id: `${snapshot.id}:${rule.id}`,
        action: "published",
        actor: snapshot.publishedBy,
        at: snapshot.effectiveFrom,
        revision: revision.revision,
        summary: `Included in ${snapshot.id}.`,
      })
    }
  }
  const latest = rule.revisions.find((revision) => revision.snapshotIds.includes(CURRENT_SNAPSHOT))
  if (!latest) {
    events.push({
      id: `${rule.id}:retired`,
      action: "retired",
      actor: "Jon Park",
      at: "2026-10-27T03:00:00Z",
      revision: null,
      summary: "Rule retired from the current snapshot.",
    })
  }
  return events.sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
}

export function policySnapshotAt(instant: string): PolicySnapshot | null {
  const time = Date.parse(instant)
  if (!Number.isFinite(time)) return null
  return policySnapshots.find((snapshot) => Date.parse(snapshot.effectiveFrom) <= time) ?? null
}

export function policySnapshotForRun(runId: string): PolicySnapshot | null {
  const decision = policyRunDecisions.find((entry) => entry.runId === runId)
  if (!decision) return null
  return policySnapshotById(decision.snapshotId) ?? policySnapshotAt(decision.at)
}

export function policyRawSnapshot(snapshotId: string): { ruleId: string; revision: number; effect: PolicyEffect; mode: PolicyMode; condition: string; hash: string }[] {
  return policyRulesForSnapshot(snapshotId).map((rule) => ({
    ruleId: rule.id,
    revision: rule.revision.revision,
    effect: rule.revision.effect,
    mode: rule.revision.mode,
    condition: rule.revision.condition,
    hash: rule.revision.hash,
  }))
}

export type PolicyListFilter = {
  q: string
  effect: PolicyEffectFilter
  mode: PolicyModeFilter
  scope: string
}

export function policyScopes(snapshotId = CURRENT_SNAPSHOT): string[] {
  return [...new Set(policyRulesForSnapshot(snapshotId).map((rule) => rule.scope))]
}

export function filterPolicyRules(rules: PolicyRuleView[], filter: PolicyListFilter): PolicyRuleView[] {
  const query = filter.q.trim().toLowerCase()
  return rules.filter((rule) => {
    if (filter.effect !== "all" && rule.revision.effect !== filter.effect) return false
    if (filter.mode !== "all" && rule.revision.mode !== filter.mode) return false
    if (filter.scope !== "all" && rule.scope !== filter.scope) return false
    if (!query) return true
    return [rule.id, rule.label, rule.area, rule.revision.condition, rule.revision.summary].some((value) =>
      value.toLowerCase().includes(query),
    )
  })
}

export function policyRuleHref(ruleId: string, snapshotId?: string | null): string {
  const params = new URLSearchParams()
  if (snapshotId && snapshotId !== CURRENT_SNAPSHOT) params.set("snapshot", snapshotId)
  const query = params.toString()
  return `/policies/rules/${encodeURIComponent(ruleId)}${query ? `?${query}` : ""}`
}

export function policyRunHref(runId: string, returnTo: string): string {
  return `/explore/r/${encodeURIComponent(runId)}?return=${encodeURIComponent(returnTo)}`
}

export function policyImpactSummary(impact: PolicyImpact): string {
  return `${formatGovernNumber(impact.replayed)} decisions replayed · ${formatGovernNumber(impact.changed)} would change`
}

export { CURRENT_SNAPSHOT as POLICY_CURRENT_SNAPSHOT, PREVIOUS_SNAPSHOT as POLICY_PREVIOUS_SNAPSHOT }

// ---------------------------------------------------------------------------
// Policies v2: status, scale, lifecycle, compare, sentence and resolver helpers
// ---------------------------------------------------------------------------

/** Runs in the reporting window. Used only for the "% of matched runs" scale. */
export const POLICY_TOTAL_RUNS_7D = 412

export function policySnapshotState(snapshotId: string): "live" | "superseded" {
  return snapshotId === CURRENT_SNAPSHOT ? "live" : "superseded"
}

export function policySnapshotRuns(snapshotId: string): PolicyRunDecision[] {
  return policyRunDecisions.filter((decision) => decision.snapshotId === snapshotId)
}

export function policySnapshotWindow(snapshotId: string): { from: string; to: string | null } {
  const index = policySnapshots.findIndex((snapshot) => snapshot.id === snapshotId)
  if (index < 0) return { from: "", to: null }
  const newer = index > 0 ? policySnapshots[index - 1]! : null
  return { from: policySnapshots[index]!.effectiveFrom, to: newer?.effectiveFrom ?? null }
}

export type PolicySnapshotChangeSummary = {
  changed: number
  unchanged: number
  added: number
  removed: number
  names: string[]
  metadataOnly: boolean
  reason: string | null
}

export function policySnapshotChangeSummary(snapshotId: string): PolicySnapshotChangeSummary {
  const diff = policySnapshotDiff(snapshotId)
  const snapshot = policySnapshotById(snapshotId)
  const metadataOnly = diff.changed.length === 0 && Boolean(snapshot?.metadataNote)
  return {
    changed: diff.changed.length,
    unchanged: diff.unchanged,
    added: diff.added,
    removed: diff.removed,
    names: diff.changed.map((rule) => rule.label),
    metadataOnly,
    reason: metadataOnly
      ? (snapshot?.metadataNote ?? "Metadata only")
      : diff.changed.length === 0
        ? "No previous snapshot to compare"
        : null,
  }
}

export function policyProvenance(snapshotId: string): { linked: number; partial: number; complete: number } {
  const runs = policySnapshotRuns(snapshotId)
  const partial = runs.filter((run) => run.provenance === "partial").length
  return { linked: runs.length, partial, complete: runs.length - partial }
}

export function policyRuleProvenance(ruleId: string): { linked: number; partial: number; complete: number } {
  const runs = policyRunDecisions.filter((run) => run.ruleId === ruleId)
  const partial = runs.filter((run) => run.provenance === "partial").length
  return { linked: runs.length, partial, complete: runs.length - partial }
}

export function policyDaysLive(snapshotId = CURRENT_SNAPSHOT): number {
  const snapshot = policySnapshotById(snapshotId)
  if (!snapshot) return 0
  return Math.max(0, Math.floor((Date.parse("2026-10-30T15:12:00Z") - Date.parse(snapshot.effectiveFrom)) / 86_400_000))
}

export type PolicyStatus = {
  tone: "ok" | "warning" | "muted"
  text: string
  caveat: string | null
  caveatDetail: string | null
}

export function policyStatusLine(snapshotId = CURRENT_SNAPSHOT): PolicyStatus {
  const snapshot = policySnapshotById(snapshotId)
  if (!snapshot) {
    return { tone: "muted", text: "No policy snapshot is recorded for this workspace.", caveat: null, caveatDetail: null }
  }
  const counts = policyModeCounts(snapshotId)
  const total = counts.enforced + counts.advisory
  const provenance = policyProvenance(snapshotId)
  const caveat =
    provenance.partial > 0
      ? `${provenance.partial} of ${provenance.linked} linked runs ${provenance.partial === 1 ? "has" : "have"} partial provenance, so fire counts may be low.`
      : null
  return {
    tone: caveat ? "warning" : "ok",
    text: `${total} rules in force (${counts.enforced} enforced, ${counts.advisory} advisory) from snapshot ${snapshot.id}, live for ${policyDaysLive(snapshotId)} ${policyDaysLive(snapshotId) === 1 ? "day" : "days"}.`,
    caveat,
    caveatDetail: caveat
      ? `${provenance.complete} of ${provenance.linked} linked runs join to certified evidence. Partial provenance means the run-to-policy join is incomplete, not that the rule was skipped.`
      : null,
  }
}

export function policyFiredDelta(rule: PolicyRule): { value: number | null; label: string; direction: "up" | "down" | "flat" | "new" } {
  if (rule.fired === null || rule.firedPrev === null) return { value: null, label: "Not reported", direction: "flat" }
  if (rule.firedPrev === 0) return { value: null, label: rule.fired > 0 ? "New" : "0%", direction: rule.fired > 0 ? "new" : "flat" }
  const value = Math.round(((rule.fired - rule.firedPrev) / rule.firedPrev) * 100)
  return {
    value,
    label: `${value > 0 ? "+" : ""}${value}%`,
    direction: value > 0 ? "up" : value < 0 ? "down" : "flat",
  }
}

export function policyRuleLastFired(ruleId: string): PolicyRunDecision | null {
  const runs = policyRunDecisions
    .filter((decision) => decision.ruleId === ruleId)
    .sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
  return runs[0] ?? null
}

export type PolicyDecisionCount = { decision: PolicyDecisionKind; label: string; count: number }

export function policyDecisionCounts(snapshotId: string | null = null, since: string | null = null): PolicyDecisionCount[] {
  const sinceTime = since ? Date.parse(since) : null
  const rows = policyRunDecisions.filter(
    (decision) =>
      (snapshotId === null || decision.snapshotId === snapshotId) &&
      (sinceTime === null || Date.parse(decision.at) >= sinceTime),
  )
  return POLICY_DECISION_ORDER.map((decision) => ({
    decision,
    label: POLICY_DECISION_LABELS[decision],
    count: rows.filter((row) => row.decision === decision).length,
  }))
}

export function policyDecisionsSince(since: string, snapshotId: string | null = null): PolicyRunDecision[] {
  const sinceTime = Date.parse(since)
  return policyRunDecisions
    .filter((decision) => Date.parse(decision.at) >= sinceTime && (snapshotId === null || decision.snapshotId === snapshotId))
    .sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
}

export type PolicyDecisionFilter = PolicyDecisionKind | "all"

export function policyDecisionLabel(decision: PolicyDecisionKind): string {
  return POLICY_DECISION_LABELS[decision]
}

export function policyChanged(rule: PolicyRuleView): boolean {
  return !rule.previousRevision || rule.previousRevision.revision !== rule.revision.revision
}

export type PolicyRuleListFilter = {
  q: string
  effect: PolicyEffectFilter
  mode: PolicyModeFilter
  area: PolicyArea | "all"
  changed: boolean
}

export function filterPolicyRulesV2(rules: PolicyRuleView[], filter: PolicyRuleListFilter): PolicyRuleView[] {
  const query = filter.q.trim().toLowerCase()
  return rules.filter((rule) => {
    if (filter.changed && !policyChanged(rule)) return false
    if (filter.effect !== "all" && rule.revision.effect !== filter.effect) return false
    if (filter.mode !== "all" && rule.revision.mode !== filter.mode) return false
    if (filter.area !== "all" && rule.area !== filter.area) return false
    if (!query) return true
    return [rule.id, rule.label, rule.area, rule.revision.condition, rule.revision.summary].some((value) =>
      value.toLowerCase().includes(query),
    )
  })
}

export function sortPolicyRules(
  rules: PolicyRuleView[],
  sort: "severity" | "name" = "severity",
): PolicyRuleView[] {
  return [...rules].sort((left, right) => {
    if (sort === "name") return left.label.localeCompare(right.label)
    const effect = POLICY_EFFECT_ORDER[left.revision.effect] - POLICY_EFFECT_ORDER[right.revision.effect]
    return effect !== 0 ? effect : left.label.localeCompare(right.label)
  })
}

export type PolicyChange = {
  id: string
  ruleId: string
  label: string
  fromRevision: number | null
  toRevision: number
  changedBy: string
  at: string
  summary: string
  effect: PolicyEffect
  snapshotId: string
}

export function policyChangeFeed(limit: number | null = null): PolicyChange[] {
  const snapshotForRevision = (revision: PolicyRuleRevision): PolicySnapshot | null =>
    policySnapshots.find((snapshot) => snapshot.effectiveFrom === revision.effectiveFrom && revision.snapshotIds.includes(snapshot.id)) ??
    policySnapshots.find((snapshot) => revision.snapshotIds.includes(snapshot.id)) ??
    null
  const changes: PolicyChange[] = []
  for (const rule of policyRules) {
    for (const revision of rule.revisions) {
      if (revision.snapshotIds.length === 0) continue
      const snapshot = snapshotForRevision(revision)
      if (!snapshot) continue
      const previous = rule.revisions.find((entry) => entry.revision === revision.revision - 1) ?? null
      changes.push({
        id: `${rule.id}@${revision.revision}`,
        ruleId: rule.id,
        label: rule.label,
        fromRevision: previous?.revision ?? null,
        toRevision: revision.revision,
        changedBy: revision.changedBy,
        at: revision.effectiveFrom,
        summary: revision.changeSummary,
        effect: revision.effect,
        snapshotId: snapshot.id,
      })
    }
  }
  const sorted = changes.sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
  return limit === null ? sorted : sorted.slice(0, limit)
}

export type PolicyLifecycleStep = {
  id: "drafted" | "validated" | "simulated" | "approved" | "live"
  label: string
  status: "done" | "pending" | "unknown"
  at: string | null
  actor: string | null
  detail: string
}

const CURRENT_LIFECYCLE: Omit<PolicyLifecycleStep, "label">[] = [
  { id: "drafted", status: "done", at: "2026-10-26T14:20:00Z", actor: "Jon Park", detail: "Draft prepared from the 24 Oct snapshot." },
  { id: "validated", status: "done", at: "2026-10-27T02:39:00Z", actor: "Policy engine", detail: "Schema validation passed for 6 rules." },
  { id: "simulated", status: "done", at: "2026-10-27T02:44:00Z", actor: "Policy engine", detail: "1,204 decisions replayed; 14 would change." },
  { id: "approved", status: "done", at: "2026-10-27T02:45:00Z", actor: "Priya Nair", detail: "Publication approved by a second operator." },
  { id: "live", status: "done", at: "2026-10-27T03:00:00Z", actor: "Jon Park", detail: "Snapshot published and enforced by the runtime." },
]

const LIFECYCLE_LABELS: Record<PolicyLifecycleStep["id"], string> = {
  drafted: "Drafted",
  validated: "Validated",
  simulated: "Simulated",
  approved: "Approved",
  live: "Live",
}

export function policySnapshotLifecycle(snapshotId: string): PolicyLifecycleStep[] {
  if (snapshotId === CURRENT_SNAPSHOT) {
    return CURRENT_LIFECYCLE.map((step) => ({ ...step, label: LIFECYCLE_LABELS[step.id] }))
  }
  const snapshot = policySnapshotById(snapshotId)
  return (Object.keys(LIFECYCLE_LABELS) as PolicyLifecycleStep["id"][]).map((id) => {
    if (id === "live" && snapshot) {
      return {
        id,
        label: LIFECYCLE_LABELS[id],
        status: "done",
        at: snapshot.effectiveFrom,
        actor: snapshot.publishedBy,
        detail: `Published as ${snapshot.id}.`,
      }
    }
    return {
      id,
      label: LIFECYCLE_LABELS[id],
      status: "unknown",
      at: null,
      actor: null,
      detail: "Not recorded for this snapshot.",
    }
  })
}

/** Registered plain-language phrases. Unregistered conditions get no sentence. */
const POLICY_CONDITION_PHRASES: Record<string, string> = {
  "spend.reserved_total > budget.limit":
    "Blocks a run when its reserved spend would push the workspace past its monthly budget.",
  "spend.month_to_date > budget.limit * 0.9":
    "A person must approve a run once the workspace reaches 90% of its monthly budget.",
  true: "Allows the action without further checks.",
  "memory.created_at < now() - interval '30 days'": "Deletes memories 30 days after they were written.",
  "memory.created_at < now() - interval '45 days'": "Deletes memories 45 days after they were written.",
  "memory.created_at < now() - interval '60 days'": "Deletes memories 60 days after they were written.",
  "source.trust != 'operator'":
    "Treats retrieved memories that do not come from an operator as data before they reach the model.",
  "tool.name == 'refund.issue'": "A person must approve every refund before the tool runs.",
  "tool.name == 'refund.issue' && tool.amount > 250":
    "A person must approve refunds above $250 before the tool runs.",
  "tool.name == 'refund.issue' && tool.amount > 200":
    "A person must approve refunds above $200 before the tool runs.",
  "model.id not in manifest.approved": "Blocks any model that is not in the approved provider manifest.",
  "pii.detected": "Marks detected personal data in prompts and completions for redaction.",
}

export function policyRuleSentence(revision: PolicyRuleRevision): string | null {
  const phrase = POLICY_CONDITION_PHRASES[revision.condition]
  if (!phrase) return null
  return revision.mode === "advisory" ? `${phrase} Only logged, not enforced.` : phrase
}

export function policyRunTotal(): number {
  return POLICY_TOTAL_RUNS_7D
}

export function policyRuleApprovalStats(ruleId: string): {
  granted: number
  denied: number
  pending: number
  medianMinutes: number | null
} {
  const approvals = policyRunDecisions
    .filter((decision) => decision.ruleId === ruleId && decision.approval)
    .map((decision) => decision.approval!)
  const granted = approvals.filter((entry) => entry.state === "granted")
  const denied = approvals.filter((entry) => entry.state === "denied").length
  const pending = approvals.filter((entry) => entry.state === "pending").length
  const minutes = granted
    .map((entry) => entry.minutes)
    .filter((value): value is number => value !== null)
    .sort((left, right) => left - right)
  const medianMinutes = minutes.length
    ? minutes.length % 2 === 1
      ? minutes[Math.floor(minutes.length / 2)]!
      : Math.round((minutes[minutes.length / 2 - 1]! + minutes[minutes.length / 2]!) / 2)
    : null
  return { granted: granted.length, denied, pending, medianMinutes }
}

export type PolicyResolveStatus = "matched" | "not_matched" | "not_evaluated"

export type PolicyResolvedRule = {
  rule: PolicyRule
  revision: PolicyRuleRevision
  status: PolicyResolveStatus
  decision: PolicyRunDecision | null
}

export type PolicyResolveRunResult = {
  runId: string
  decision: PolicyRunDecision
  snapshot: PolicySnapshot
  rules: PolicyResolvedRule[]
}

function resolvedRulesFor(snapshotId: string, decision: PolicyRunDecision | null): PolicyResolvedRule[] {
  return policyRules.map((rule) => {
    const revision =
      rule.revisions.find((entry) => entry.revision === (decision?.ruleId === rule.id ? decision.ruleRevision : -1)) ??
      rule.revisions.find((entry) => entry.snapshotIds.includes(snapshotId)) ??
      rule.revisions[0]!
    const matched = decision?.ruleId === rule.id
    return {
      rule,
      revision,
      status: matched ? "matched" : "not_evaluated",
      decision: matched ? decision : null,
    }
  })
}

export function policyResolveRun(runId: string): PolicyResolveRunResult | null {
  const decision = policyRunDecisions.find((entry) => entry.runId === runId)
  if (!decision) return null
  const snapshot = policySnapshotById(decision.snapshotId) ?? policySnapshotAt(decision.at)
  if (!snapshot) return null
  return { runId, decision, snapshot, rules: resolvedRulesFor(snapshot.id, decision) }
}

export function policyResolveAt(instant: string): { snapshot: PolicySnapshot; rules: PolicyResolvedRule[] } | null {
  const snapshot = policySnapshotAt(instant)
  if (!snapshot) return null
  return { snapshot, rules: resolvedRulesFor(snapshot.id, null) }
}

export type PolicyCompareStatus = "changed" | "unchanged" | "added" | "removed"

export type PolicyCompareRule = {
  rule: PolicyRule
  fromRevision: PolicyRuleRevision | null
  toRevision: PolicyRuleRevision | null
  status: PolicyCompareStatus
  sections: SectionDiff[]
  changedKeys: string[]
}

export type PolicyCompareResult = {
  from: PolicySnapshot
  to: PolicySnapshot
  rules: PolicyCompareRule[]
  changed: number
  unchanged: number
  added: number
  removed: number
}

function compareRevisionSections(
  from: PolicyRuleRevision | null,
  to: PolicyRuleRevision | null,
): SectionDiff[] {
  const labels = ["Effect", "Mode", "Condition", "Summary"] as const
  const lineOf = (revision: PolicyRuleRevision, index: number) => {
    switch (index) {
      case 0:
        return `Effect: ${POLICY_EFFECT_LABELS[revision.effect]}`
      case 1:
        return `Mode: ${POLICY_MODE_LABELS[revision.mode]}`
      case 2:
        return `Condition: ${revision.condition}`
      default:
        return `Summary: ${revision.summary}`
    }
  }
  return diffDirectiveSections(
    labels.map((label, index) => ({
      id: label.toLowerCase(),
      label,
      lines: from ? [lineOf(from, index)] : [],
    })),
    labels.map((label, index) => ({
      id: label.toLowerCase(),
      label,
      lines: to ? [lineOf(to, index)] : [],
    })),
  )
}

const COMPARE_STATUS_ORDER: Record<PolicyCompareStatus, number> = {
  changed: 0,
  added: 1,
  removed: 2,
  unchanged: 3,
}

/** Compares two recorded snapshots rule by rule. Unrecorded snapshots return null. */
export function policyCompare(fromId: string, toId: string): PolicyCompareResult | null {
  const from = policySnapshotById(fromId)
  const to = policySnapshotById(toId)
  if (!from || !to) return null
  const beforeRules = new Map(policyRulesForSnapshot(from.id).map((view) => [view.id, view]))
  const afterRules = new Map(policyRulesForSnapshot(to.id).map((view) => [view.id, view]))
  const ids = [...new Set([...beforeRules.keys(), ...afterRules.keys()])]
  const rules = ids.map<PolicyCompareRule>((id) => {
    const before = beforeRules.get(id) ?? null
    const after = afterRules.get(id) ?? null
    const rule = (after ?? before)!
    const fromRevision = before?.revision ?? null
    const toRevision = after?.revision ?? null
    const status: PolicyCompareStatus = !fromRevision
      ? "added"
      : !toRevision
        ? "removed"
        : fromRevision.revision === toRevision.revision
          ? "unchanged"
          : "changed"
    const sections = status === "unchanged" ? [] : compareRevisionSections(fromRevision, toRevision)
    return {
      rule,
      fromRevision,
      toRevision,
      status,
      sections,
      changedKeys: sections.filter((section) => section.changed).map((section) => section.label),
    }
  })
  rules.sort(
    (left, right) =>
      COMPARE_STATUS_ORDER[left.status] - COMPARE_STATUS_ORDER[right.status] ||
      left.rule.label.localeCompare(right.rule.label),
  )
  return {
    from,
    to,
    rules,
    changed: rules.filter((rule) => rule.status === "changed").length,
    unchanged: rules.filter((rule) => rule.status === "unchanged").length,
    added: rules.filter((rule) => rule.status === "added").length,
    removed: rules.filter((rule) => rule.status === "removed").length,
  }
}

export function policyRevisionSections(rule: PolicyRule, revisionNumber: number): SectionDiff[] {
  const revision = rule.revisions.find((entry) => entry.revision === revisionNumber)
  if (!revision) return []
  const previous = rule.revisions.find((entry) => entry.revision === revisionNumber - 1) ?? null
  const linesFor = (value: PolicyRuleRevision) => [
    `Effect: ${POLICY_EFFECT_LABELS[value.effect]}`,
    `Mode: ${POLICY_MODE_LABELS[value.mode]}`,
    `Condition: ${value.condition}`,
    `Summary: ${value.summary}`,
    `Changed by: ${value.changedBy}`,
    `Change note: ${value.changeSummary}`,
  ]
  return diffDirectiveSections(
    previous ? [{ id: "revision", label: "Revision", lines: linesFor(previous) }] : [],
    [{ id: "revision", label: "Revision", lines: linesFor(revision) }],
  )
}

export function policySnapshotJson(snapshotId: string): Record<string, unknown> {
  const snapshot = policySnapshotById(snapshotId)
  if (!snapshot) return {}
  return {
    id: snapshot.id,
    effective_from: snapshot.effectiveFrom,
    published_at: snapshot.publishedAt,
    published_by: snapshot.publishedBy,
    digest: snapshot.digest,
    previous_id: snapshot.previousId,
    previous_digest: snapshot.previousDigest,
    message: snapshot.message,
    rules: policyRawSnapshot(snapshotId),
  }
}
