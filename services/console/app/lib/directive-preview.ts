import { diffDirectiveSections, diffSummary, type SectionDiff, type DiffSummary } from "./govern-diff"
import { formatGovernWait, GOVERN_NOW } from "./govern-format"

export type DirectiveState = "draft" | "candidate" | "live" | "superseded" | "rejected" | "rolled_back"
export type DirectiveTab = "overview" | "versions" | "diff" | "promotion" | "usage" | "audit"
export type DirectiveSortKey = "name" | "change" | "live"
export type DirectiveStateFilter = DirectiveState | "all"

export const DIRECTIVE_TABS: { id: DirectiveTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "versions", label: "Versions" },
  { id: "diff", label: "Diff" },
  { id: "promotion", label: "Promotion" },
  { id: "usage", label: "Usage" },
  { id: "audit", label: "Audit" },
]

export const DIRECTIVE_STATE_LABELS: Record<DirectiveState, string> = {
  draft: "Draft",
  candidate: "Candidate",
  live: "Live",
  superseded: "Superseded",
  rejected: "Rejected",
  rolled_back: "Rolled back",
}

export const DIRECTIVE_STATE_FILTER_LABELS: Record<DirectiveStateFilter, string> = {
  all: "All states",
  ...DIRECTIVE_STATE_LABELS,
}

export type DirectiveCheckState = "passed" | "pending" | "failed" | "skipped" | "not_configured"

export type DirectiveCheck = {
  id: string
  name: string
  state: DirectiveCheckState
  result: string | null
  actor: string | null
  at: string | null
  evidence: { label: string; href: string } | null
}

export type DirectiveSection = {
  id: string
  label: string
  lines: string[]
}

export type DirectiveApproval = {
  actor: string
  at: string
  decision: "approved" | "changes_requested"
}

export type DirectiveVersion = {
  version: string
  state: DirectiveState
  author: string
  createdAt: string
  approvedBy: string | null
  approvedAt: string | null
  liveFrom: string | null
  liveTo: string | null
  summary: string | null
  hash: string
  eventId: string
  sections: DirectiveSection[]
  riskFlags: string[]
  checks: DirectiveCheck[]
  approvalsRequired: number
  approvals: DirectiveApproval[]
  eligibleApprovers: string[]
  rollbackReason: string | null
}

export type DirectiveEventAction =
  | "created"
  | "submitted"
  | "check_passed"
  | "check_failed"
  | "approved"
  | "changes_requested"
  | "promoted"
  | "rolled_back"
  | "rejected"

export type DirectiveEvent = {
  id: string
  action: DirectiveEventAction
  actor: string
  at: string
  version: string
  summary: string
  evidenceId: string
}

export type DirectiveUsage = {
  sessionsByVersion: { version: string; sessions: number; errorRate: number | null }[] | null
  errorRateByVersion: { version: string; errorRate: number; baselineErrorRate: number }[] | null
}

export type DirectiveScope = {
  org: string
  workspace: string
  area: string
}

export type DirectiveAgentRef = {
  id: string
  name: string
}

export type Directive = {
  id: string
  name: string
  description: string
  scope: DirectiveScope
  agents: DirectiveAgentRef[]
  versions: DirectiveVersion[]
  events: DirectiveEvent[]
  usage: DirectiveUsage
}

export const DIRECTIVE_EVENT_LABELS: Record<DirectiveEventAction, string> = {
  created: "Candidate created",
  submitted: "Submitted for approval",
  check_passed: "Check passed",
  check_failed: "Check failed",
  approved: "Approved",
  changes_requested: "Changes requested",
  promoted: "Promoted to live",
  rolled_back: "Rolled back",
  rejected: "Rejected",
}

const HASH_BASE = "9f2a61c4a7b0d3e8f1c25a4936b7d8e0f1a2b3c4d5e6f708192a3b4c5d6e7f89"

function digest(suffix: string): string {
  return `sha256:${HASH_BASE.slice(0, 56)}${suffix}`
}

const CHECK_HREF = (id: string): string => `/audit?event=${encodeURIComponent(id)}`

function supportSections(refundRule: string, autoRunRule: string): DirectiveSection[] {
  return [
    {
      id: "identity",
      label: "Identity",
      lines: [
        "You are the support triage agent for workspace ws_42.",
        "Resolve customer requests using the support tools and the billing ledger.",
      ],
    },
    {
      id: "constraints",
      label: "Constraints",
      lines: [
        "Never promise a refund without checking the billing ledger.",
        refundRule,
        "Never disclose internal policy identifiers to a customer.",
      ],
    },
    {
      id: "tool_policy",
      label: "Tool policy",
      lines: [
        "Read tools may run without approval.",
        autoRunRule,
        "ticket.update may append notes without approval.",
      ],
    },
    {
      id: "output_contract",
      label: "Output contract",
      lines: [
        "State the charge status, idempotency key, and next action.",
        "Cite the policy check that allowed or blocked the action.",
      ],
    },
  ]
}

function billingSections(exportScope: string): DirectiveSection[] {
  return [
    {
      id: "identity",
      label: "Identity",
      lines: ["You are the billing analyst for workspace ws_42.", "Reconcile invoices and explain billing changes."],
    },
    {
      id: "constraints",
      label: "Constraints",
      lines: [
        "Never send an invoice outside the approved billing domain.",
        "Never export customer payment details in a plain-text file.",
      ],
    },
    {
      id: "tool_policy",
      label: "Tool policy",
      lines: ["Read tools may run without approval.", exportScope],
    },
    {
      id: "output_contract",
      label: "Output contract",
      lines: ["State the invoice id, settlement window, and next action."],
    },
  ]
}

function onboardingSections(): DirectiveSection[] {
  return [
    {
      id: "identity",
      label: "Identity",
      lines: ["You are the onboarding guide for workspace ws_42.", "Help new members find the right team and first task."],
    },
    {
      id: "constraints",
      label: "Constraints",
      lines: ["Never share another member's profile or private notes.", "Link to public docs instead of pasting internal pages."],
    },
    {
      id: "tool_policy",
      label: "Tool policy",
      lines: ["Directory lookups may run without approval.", "Invites always require an operator approval."],
    },
    {
      id: "output_contract",
      label: "Output contract",
      lines: ["State the suggested team, first task, and the doc that explains it."],
    },
  ]
}

function incidentSections(pagingRule: string): DirectiveSection[] {
  return [
    {
      id: "identity",
      label: "Identity",
      lines: ["You are the incident responder for workspace ws_42.", "Classify severity and route incidents to the on-call owner."],
    },
    {
      id: "constraints",
      label: "Constraints",
      lines: ["Never acknowledge an incident without naming an owner.", "Never close an incident before the mitigation is recorded."],
    },
    {
      id: "tool_policy",
      label: "Tool policy",
      lines: ["Read tools may run without approval.", pagingRule],
    },
    {
      id: "output_contract",
      label: "Output contract",
      lines: ["State the severity, owner, mitigation, and next checkpoint."],
    },
  ]
}

const supportChecksApproved: DirectiveCheck[] = [
  {
    id: "schema",
    name: "Schema and section validation",
    state: "passed",
    result: "4 sections valid · no unknown keys",
    actor: "directive-linter",
    at: "2026-10-24T08:52:00Z",
    evidence: { label: "evt_c1d904", href: CHECK_HREF("evt_c1d904") },
  },
  {
    id: "injection",
    name: "Prompt-injection review",
    state: "passed",
    result: "No instruction-boundary findings",
    actor: "Eval run eval_71ca",
    at: "2026-10-24T08:56:00Z",
    evidence: { label: "evt_a42f18", href: CHECK_HREF("evt_a42f18") },
  },
  {
    id: "budget",
    name: "Budget impact",
    state: "passed",
    result: "Projected spend within the workspace reservation",
    actor: "Policy replay",
    at: "2026-10-24T09:01:00Z",
    evidence: { label: "evt_8e30bd", href: CHECK_HREF("evt_8e30bd") },
  },
  {
    id: "approval",
    name: "Approval and rollout plan",
    state: "passed",
    result: "Approved by Mira Chen",
    actor: "Mira Chen",
    at: "2026-10-24T09:02:00Z",
    evidence: { label: "evt_4c81ee", href: CHECK_HREF("evt_4c81ee") },
  },
]

const supportChecksCandidate: DirectiveCheck[] = [
  {
    id: "schema",
    name: "Schema and section validation",
    state: "passed",
    result: "4 sections valid · no unknown keys",
    actor: "directive-linter",
    at: "2026-10-27T14:13:00Z",
    evidence: { label: "evt_2b7c11", href: CHECK_HREF("evt_2b7c11") },
  },
  {
    id: "injection",
    name: "Prompt-injection review",
    state: "passed",
    result: "No instruction-boundary findings",
    actor: "Eval run eval_9c31",
    at: "2026-10-27T14:15:00Z",
    evidence: { label: "evt_7e4d92", href: CHECK_HREF("evt_7e4d92") },
  },
  {
    id: "budget",
    name: "Budget impact",
    state: "passed",
    result: "Projected spend within the workspace reservation",
    actor: "Policy replay",
    at: "2026-10-27T14:18:00Z",
    evidence: { label: "evt_6d20aa", href: CHECK_HREF("evt_6d20aa") },
  },
  {
    id: "approval",
    name: "Approval and rollout plan",
    state: "pending",
    result: "1 approval required",
    actor: null,
    at: null,
    evidence: null,
  },
]

const billingChecksCandidate: DirectiveCheck[] = [
  {
    id: "schema",
    name: "Schema and section validation",
    state: "passed",
    result: "4 sections valid · no unknown keys",
    actor: "directive-linter",
    at: "2026-10-27T16:41:00Z",
    evidence: { label: "evt_0f4a83", href: CHECK_HREF("evt_0f4a83") },
  },
  {
    id: "injection",
    name: "Prompt-injection review",
    state: "passed",
    result: "No instruction-boundary findings",
    actor: "Eval run eval_3bb1",
    at: "2026-10-27T16:44:00Z",
    evidence: { label: "evt_63d1c7", href: CHECK_HREF("evt_63d1c7") },
  },
  {
    id: "budget",
    name: "Budget impact",
    state: "failed",
    result: "Projected spend exceeds the workspace reservation by $180",
    actor: "Policy replay",
    at: "2026-10-27T16:48:00Z",
    evidence: { label: "evt_ba9204", href: CHECK_HREF("evt_ba9204") },
  },
  {
    id: "approval",
    name: "Approval and rollout plan",
    state: "skipped",
    result: "Blocked by a failed check",
    actor: null,
    at: null,
    evidence: null,
  },
]

const incidentChecksRejected: DirectiveCheck[] = [
  {
    id: "schema",
    name: "Schema and section validation",
    state: "passed",
    result: "4 sections valid · no unknown keys",
    actor: "directive-linter",
    at: "2026-10-20T10:02:00Z",
    evidence: { label: "evt_5ac7d0", href: CHECK_HREF("evt_5ac7d0") },
  },
  {
    id: "injection",
    name: "Prompt-injection review",
    state: "passed",
    result: "No instruction-boundary findings",
    actor: "Eval run eval_8ad0",
    at: "2026-10-20T10:05:00Z",
    evidence: { label: "evt_17b3e6", href: CHECK_HREF("evt_17b3e6") },
  },
  {
    id: "budget",
    name: "Budget impact",
    state: "passed",
    result: "Projected spend within the workspace reservation",
    actor: "Policy replay",
    at: "2026-10-20T10:08:00Z",
    evidence: { label: "evt_42ce91", href: CHECK_HREF("evt_42ce91") },
  },
  {
    id: "approval",
    name: "Human approval for paging",
    state: "failed",
    result: "Automated paging requires a human decision",
    actor: "Policy reviewer",
    at: "2026-10-20T10:12:00Z",
    evidence: { label: "evt_90f2a4", href: CHECK_HREF("evt_90f2a4") },
  },
]

const supportTriage: Directive = {
  id: "dir_support_triage",
  name: "Support triage",
  description: "Customer triage, refunds, and billing-ledger checks for the support workspace.",
  scope: { org: "org_demo_42", workspace: "ws_42", area: "support" },
  agents: [
    { id: "ag_support_triage", name: "Support triage" },
    { id: "ag_escalation_router", name: "Escalation router" },
    { id: "ag_policy_reviewer", name: "Policy reviewer" },
  ],
  usage: { sessionsByVersion: null, errorRateByVersion: null },
  versions: [
    {
      version: "v14",
      state: "candidate",
      author: "Mira Chen",
      createdAt: "2026-10-27T14:12:00Z",
      approvedBy: null,
      approvedAt: null,
      liveFrom: null,
      liveTo: null,
      summary: "Refunds of any amount now require approval and billing.create_refund always asks a person.",
      hash: digest("c81e0a1b"),
      eventId: "evt_1a0712",
      sections: supportSections("Refunds of any amount require an operator approval.", "billing.create_refund always requests approval."),
      riskFlags: [
        "Removes the $200 auto-run threshold on billing.create_refund, a money-moving tool.",
        "Every refund now needs a person, including small credits.",
      ],
      checks: supportChecksCandidate,
      approvalsRequired: 1,
      approvals: [],
      eligibleApprovers: ["Mira Chen", "Jon Park", "Priya Nair"],
      rollbackReason: null,
    },
    {
      version: "v13",
      state: "live",
      author: "Jon Park",
      createdAt: "2026-10-24T08:50:00Z",
      approvedBy: "Mira Chen",
      approvedAt: "2026-10-24T09:02:00Z",
      liveFrom: "2026-10-24T09:18:00Z",
      liveTo: null,
      summary: "Added a $200 auto-run threshold for refunds and clarified idempotency reporting.",
      hash: digest("5d2c94a7"),
      eventId: "evt_0b3c55",
      sections: supportSections("Refunds above $200 require an operator approval.", "billing.create_refund may auto-run below $200."),
      riskFlags: [],
      checks: supportChecksApproved,
      approvalsRequired: 1,
      approvals: [{ actor: "Mira Chen", at: "2026-10-24T09:02:00Z", decision: "approved" }],
      eligibleApprovers: ["Mira Chen", "Priya Nair"],
      rollbackReason: null,
    },
    {
      version: "v12",
      state: "superseded",
      author: "Mira Chen",
      createdAt: "2026-10-18T10:55:00Z",
      approvedBy: "Jon Park",
      approvedAt: "2026-10-18T11:10:00Z",
      liveFrom: "2026-10-18T11:22:00Z",
      liveTo: "2026-10-24T09:18:00Z",
      summary: "Raised the refund approval threshold from $100 to $150.",
      hash: digest("88b1f304"),
      eventId: "evt_77b031",
      sections: supportSections("Refunds above $150 require an operator approval.", "billing.create_refund may auto-run below $150."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Jon Park", at: "2026-10-18T11:10:00Z", decision: "approved" }],
      eligibleApprovers: ["Jon Park", "Priya Nair"],
      rollbackReason: null,
    },
    {
      version: "v11",
      state: "superseded",
      author: "Jon Park",
      createdAt: "2026-10-11T08:40:00Z",
      approvedBy: "Mira Chen",
      approvedAt: "2026-10-11T08:55:00Z",
      liveFrom: "2026-10-11T09:02:00Z",
      liveTo: "2026-10-18T11:22:00Z",
      summary: "Raised the refund approval threshold from $75 to $100.",
      hash: digest("3e7a0d92"),
      eventId: "evt_3a8f04",
      sections: supportSections("Refunds above $100 require an operator approval.", "billing.create_refund may auto-run below $100."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Mira Chen", at: "2026-10-11T08:55:00Z", decision: "approved" }],
      eligibleApprovers: ["Mira Chen", "Priya Nair"],
      rollbackReason: null,
    },
    {
      version: "v10",
      state: "superseded",
      author: "Mira Chen",
      createdAt: "2026-10-03T09:10:00Z",
      approvedBy: "Jon Park",
      approvedAt: "2026-10-03T09:20:00Z",
      liveFrom: "2026-10-03T09:26:00Z",
      liveTo: "2026-10-11T09:02:00Z",
      summary: "Raised the refund approval threshold from $50 to $75.",
      hash: digest("a10d6b47"),
      eventId: "evt_92d6c1",
      sections: supportSections("Refunds above $75 require an operator approval.", "billing.create_refund may auto-run below $75."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Jon Park", at: "2026-10-03T09:20:00Z", decision: "approved" }],
      eligibleApprovers: ["Jon Park", "Priya Nair"],
      rollbackReason: null,
    },
    {
      version: "v9",
      state: "superseded",
      author: "Jon Park",
      createdAt: "2026-09-27T10:05:00Z",
      approvedBy: "Mira Chen",
      approvedAt: "2026-09-27T10:12:00Z",
      liveFrom: "2026-09-27T10:20:00Z",
      liveTo: "2026-10-03T09:26:00Z",
      summary: "Initial support-triage directive.",
      hash: digest("6c3e7a18"),
      eventId: "evt_5c1902",
      sections: supportSections("Refunds above $50 require an operator approval.", "billing.create_refund may auto-run below $50."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Mira Chen", at: "2026-09-27T10:12:00Z", decision: "approved" }],
      eligibleApprovers: ["Mira Chen", "Priya Nair"],
      rollbackReason: null,
    },
  ],
  events: [
    { id: "evt_1a0712", action: "created", actor: "Mira Chen", at: "2026-10-27T14:12:00Z", version: "v14", summary: "Candidate v14 created from live v13.", evidenceId: "evt_1a0712" },
    { id: "evt_2b7c11", action: "check_passed", actor: "directive-linter", at: "2026-10-27T14:13:00Z", version: "v14", summary: "Schema and section validation passed.", evidenceId: "evt_2b7c11" },
    { id: "evt_7e4d92", action: "check_passed", actor: "Eval run eval_9c31", at: "2026-10-27T14:15:00Z", version: "v14", summary: "Prompt-injection review passed.", evidenceId: "evt_7e4d92" },
    { id: "evt_6d20aa", action: "check_passed", actor: "Policy replay", at: "2026-10-27T14:18:00Z", version: "v14", summary: "Budget impact stayed within the workspace reservation.", evidenceId: "evt_6d20aa" },
    { id: "evt_9f2a61", action: "promoted", actor: "Jon Park", at: "2026-10-24T09:18:00Z", version: "v13", summary: "Promoted v13 to live.", evidenceId: "evt_9f2a61" },
    { id: "evt_4c81ee", action: "approved", actor: "Mira Chen", at: "2026-10-24T09:02:00Z", version: "v13", summary: "Approved v13 for promotion.", evidenceId: "evt_4c81ee" },
    { id: "evt_0b3c55", action: "created", actor: "Jon Park", at: "2026-10-24T08:50:00Z", version: "v13", summary: "Candidate v13 created from live v12.", evidenceId: "evt_0b3c55" },
    { id: "evt_c1d904", action: "check_passed", actor: "directive-linter", at: "2026-10-24T08:52:00Z", version: "v13", summary: "Schema and section validation passed.", evidenceId: "evt_c1d904" },
    { id: "evt_a42f18", action: "check_passed", actor: "Eval run eval_71ca", at: "2026-10-24T08:56:00Z", version: "v13", summary: "Prompt-injection review passed.", evidenceId: "evt_a42f18" },
    { id: "evt_8e30bd", action: "check_passed", actor: "Policy replay", at: "2026-10-24T09:01:00Z", version: "v13", summary: "Budget impact stayed within the workspace reservation.", evidenceId: "evt_8e30bd" },
    { id: "evt_77b031", action: "promoted", actor: "Mira Chen", at: "2026-10-18T11:22:00Z", version: "v12", summary: "Promoted v12 to live.", evidenceId: "evt_77b031" },
    { id: "evt_5e19a2", action: "approved", actor: "Jon Park", at: "2026-10-18T11:10:00Z", version: "v12", summary: "Approved v12 for promotion.", evidenceId: "evt_5e19a2" },
    { id: "evt_3a8f04", action: "promoted", actor: "Jon Park", at: "2026-10-11T09:02:00Z", version: "v11", summary: "Promoted v11 to live.", evidenceId: "evt_3a8f04" },
    { id: "evt_92d6c1", action: "promoted", actor: "Mira Chen", at: "2026-10-03T09:26:00Z", version: "v10", summary: "Promoted v10 to live.", evidenceId: "evt_92d6c1" },
    { id: "evt_5c1902", action: "promoted", actor: "Jon Park", at: "2026-09-27T10:20:00Z", version: "v9", summary: "Promoted v9 to live.", evidenceId: "evt_5c1902" },
  ],
}

const billingAssistant: Directive = {
  id: "dir_billing_assistant",
  name: "Billing assistant",
  description: "Invoice reconciliation, billing explanations, and approved export boundaries.",
  scope: { org: "org_demo_42", workspace: "ws_42", area: "billing" },
  agents: [
    { id: "ag_billing_analyst", name: "Billing analyst" },
    { id: "ag_compliance_auditor", name: "Compliance auditor" },
  ],
  usage: { sessionsByVersion: null, errorRateByVersion: null },
  versions: [
    {
      version: "v9",
      state: "candidate",
      author: "Priya Nair",
      createdAt: "2026-10-27T16:40:00Z",
      approvedBy: null,
      approvedAt: null,
      liveFrom: null,
      liveTo: null,
      summary: "Adds cross-workspace ledger export for reconciliation.",
      hash: digest("0f4a83c2"),
      eventId: "evt_0f4a83",
      sections: billingSections("ledger.export may export across all workspaces inside the organization."),
      riskFlags: ["Broadens ledger export beyond the billing workspace."],
      checks: billingChecksCandidate,
      approvalsRequired: 1,
      approvals: [],
      eligibleApprovers: ["Jon Park", "Mira Chen"],
      rollbackReason: null,
    },
    {
      version: "v8",
      state: "live",
      author: "Marcus Lee",
      createdAt: "2026-10-14T09:05:00Z",
      approvedBy: "Priya Nair",
      approvedAt: "2026-10-14T09:12:00Z",
      liveFrom: "2026-10-14T09:20:00Z",
      liveTo: null,
      summary: "Adds CSV export for approved invoice summaries.",
      hash: digest("b7d2e941"),
      eventId: "evt_b7d2e9",
      sections: billingSections("ledger.export may run only inside the billing workspace."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Priya Nair", at: "2026-10-14T09:12:00Z", decision: "approved" }],
      eligibleApprovers: ["Priya Nair", "Jon Park"],
      rollbackReason: null,
    },
    {
      version: "v7",
      state: "superseded",
      author: "Marcus Lee",
      createdAt: "2026-09-30T13:20:00Z",
      approvedBy: "Priya Nair",
      approvedAt: "2026-09-30T13:24:00Z",
      liveFrom: "2026-09-30T13:30:00Z",
      liveTo: "2026-10-14T09:20:00Z",
      summary: "Initial billing reconciliation directive.",
      hash: digest("2a9c60f3"),
      eventId: "evt_2a9c60",
      sections: billingSections("ledger.export may run only inside the billing workspace."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Priya Nair", at: "2026-09-30T13:24:00Z", decision: "approved" }],
      eligibleApprovers: ["Priya Nair", "Jon Park"],
      rollbackReason: null,
    },
  ],
  events: [
    { id: "evt_0f4a83", action: "created", actor: "Priya Nair", at: "2026-10-27T16:40:00Z", version: "v9", summary: "Candidate v9 created from live v8.", evidenceId: "evt_0f4a83" },
    { id: "evt_63d1c7", action: "check_passed", actor: "Eval run eval_3bb1", at: "2026-10-27T16:44:00Z", version: "v9", summary: "Prompt-injection review passed.", evidenceId: "evt_63d1c7" },
    { id: "evt_ba9204", action: "check_failed", actor: "Policy replay", at: "2026-10-27T16:48:00Z", version: "v9", summary: "Budget impact exceeds the workspace reservation by $180.", evidenceId: "evt_ba9204" },
    { id: "evt_b7d2e9", action: "promoted", actor: "Marcus Lee", at: "2026-10-14T09:20:00Z", version: "v8", summary: "Promoted v8 to live.", evidenceId: "evt_b7d2e9" },
    { id: "evt_2a9c60", action: "promoted", actor: "Marcus Lee", at: "2026-09-30T13:30:00Z", version: "v7", summary: "Promoted v7 to live.", evidenceId: "evt_2a9c60" },
  ],
}

const onboardingGuide: Directive = {
  id: "dir_onboarding_guide",
  name: "Onboarding guide",
  description: "First-week guidance, team routing, and safe documentation links.",
  scope: { org: "org_demo_42", workspace: "ws_42", area: "onboarding" },
  agents: [{ id: "ag_onboarding_guide", name: "Onboarding guide" }],
  usage: { sessionsByVersion: null, errorRateByVersion: null },
  versions: [
    {
      version: "v1",
      state: "live",
      author: "Hana T.",
      createdAt: "2026-10-09T10:15:00Z",
      approvedBy: "Jon Park",
      approvedAt: "2026-10-09T10:22:00Z",
      liveFrom: "2026-10-09T10:30:00Z",
      liveTo: null,
      summary: "Initial onboarding directive.",
      hash: digest("d41e7b20"),
      eventId: "evt_d41e7b",
      sections: onboardingSections(),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Jon Park", at: "2026-10-09T10:22:00Z", decision: "approved" }],
      eligibleApprovers: ["Jon Park", "Priya Nair"],
      rollbackReason: null,
    },
  ],
  events: [
    { id: "evt_d41e7b", action: "promoted", actor: "Hana T.", at: "2026-10-09T10:30:00Z", version: "v1", summary: "Promoted v1 to live.", evidenceId: "evt_d41e7b" },
  ],
}

const incidentResponder: Directive = {
  id: "dir_incident_responder",
  name: "Incident responder",
  description: "Severity classification, owner routing, and mitigation handoff for production incidents.",
  scope: { org: "org_demo_42", workspace: "ws_42", area: "reliability" },
  agents: [
    { id: "ag_escalation_router", name: "Escalation router" },
    { id: "ag_policy_reviewer", name: "Policy reviewer" },
  ],
  usage: { sessionsByVersion: null, errorRateByVersion: null },
  versions: [
    {
      version: "v6",
      state: "rejected",
      author: "Jon Park",
      createdAt: "2026-10-20T10:00:00Z",
      approvedBy: null,
      approvedAt: null,
      liveFrom: null,
      liveTo: null,
      summary: "Adds automated paging for severity-1 incidents.",
      hash: digest("5ac7d0e1"),
      eventId: "evt_5ac7d0",
      sections: incidentSections("trigger.pager may open incidents without approval."),
      riskFlags: ["Lets the agent page humans without an approval."],
      checks: incidentChecksRejected,
      approvalsRequired: 1,
      approvals: [],
      eligibleApprovers: ["Priya Nair", "Mira Chen"],
      rollbackReason: null,
    },
    {
      version: "v5",
      state: "live",
      author: "Priya Nair",
      createdAt: "2026-10-21T11:40:00Z",
      approvedBy: "Jon Park",
      approvedAt: "2026-10-21T11:52:00Z",
      liveFrom: "2026-10-21T12:00:00Z",
      liveTo: null,
      summary: "Clarifies severity levels and escalation handoff.",
      hash: digest("f0a63d8c"),
      eventId: "evt_f0a63d",
      sections: incidentSections("Paging a human always requires an operator approval."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Jon Park", at: "2026-10-21T11:52:00Z", decision: "approved" }],
      eligibleApprovers: ["Jon Park", "Mira Chen"],
      rollbackReason: null,
    },
    {
      version: "v4",
      state: "superseded",
      author: "Jon Park",
      createdAt: "2026-10-12T14:10:00Z",
      approvedBy: "Priya Nair",
      approvedAt: "2026-10-12T14:18:00Z",
      liveFrom: "2026-10-12T14:24:00Z",
      liveTo: "2026-10-21T12:00:00Z",
      summary: "Adds a human approval gate before paging.",
      hash: digest("9d27b4e0"),
      eventId: "evt_9d27b4",
      sections: incidentSections("Paging a human always requires an operator approval."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Priya Nair", at: "2026-10-12T14:18:00Z", decision: "approved" }],
      eligibleApprovers: ["Priya Nair", "Mira Chen"],
      rollbackReason: null,
    },
    {
      version: "v3",
      state: "rolled_back",
      author: "Mira Chen",
      createdAt: "2026-10-06T09:05:00Z",
      approvedBy: "Jon Park",
      approvedAt: "2026-10-06T09:10:00Z",
      liveFrom: "2026-10-06T09:16:00Z",
      liveTo: "2026-10-12T14:24:00Z",
      summary: "Automated paging for severity-1 incidents.",
      hash: digest("3c8e1a75"),
      eventId: "evt_3c8e1a",
      sections: incidentSections("trigger.pager may open incidents without approval."),
      riskFlags: ["Let the agent page humans without an approval."],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Jon Park", at: "2026-10-06T09:10:00Z", decision: "approved" }],
      eligibleApprovers: ["Jon Park", "Priya Nair"],
      rollbackReason: "Automated paging opened duplicate incidents.",
    },
    {
      version: "v2",
      state: "superseded",
      author: "Jon Park",
      createdAt: "2026-09-22T15:30:00Z",
      approvedBy: "Mira Chen",
      approvedAt: "2026-09-22T15:36:00Z",
      liveFrom: "2026-09-22T15:42:00Z",
      liveTo: "2026-10-06T09:16:00Z",
      summary: "Adds severity classification for production incidents.",
      hash: digest("8b40d2f6"),
      eventId: "evt_8b40d2",
      sections: incidentSections("Paging a human always requires an operator approval."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Mira Chen", at: "2026-09-22T15:36:00Z", decision: "approved" }],
      eligibleApprovers: ["Mira Chen", "Priya Nair"],
      rollbackReason: null,
    },
    {
      version: "v1",
      state: "superseded",
      author: "Mira Chen",
      createdAt: "2026-09-12T11:00:00Z",
      approvedBy: "Jon Park",
      approvedAt: "2026-09-12T11:06:00Z",
      liveFrom: "2026-09-12T11:12:00Z",
      liveTo: "2026-09-22T15:42:00Z",
      summary: "Initial incident-responder directive.",
      hash: digest("e2f7a6b9"),
      eventId: "evt_e2f7a6",
      sections: incidentSections("Paging a human always requires an operator approval."),
      riskFlags: [],
      checks: [],
      approvalsRequired: 1,
      approvals: [{ actor: "Jon Park", at: "2026-09-12T11:06:00Z", decision: "approved" }],
      eligibleApprovers: ["Jon Park", "Priya Nair"],
      rollbackReason: null,
    },
  ],
  events: [
    { id: "evt_5ac7d0", action: "created", actor: "Jon Park", at: "2026-10-20T10:00:00Z", version: "v6", summary: "Candidate v6 created from live v5.", evidenceId: "evt_5ac7d0" },
    { id: "evt_90f2a4", action: "rejected", actor: "Policy reviewer", at: "2026-10-20T10:12:00Z", version: "v6", summary: "Rejected: automated paging requires a human decision.", evidenceId: "evt_90f2a4" },
    { id: "evt_f0a63d", action: "promoted", actor: "Priya Nair", at: "2026-10-21T12:00:00Z", version: "v5", summary: "Promoted v5 to live.", evidenceId: "evt_f0a63d" },
    { id: "evt_9d27b4", action: "promoted", actor: "Jon Park", at: "2026-10-12T14:24:00Z", version: "v4", summary: "Promoted v4 to live after rolling back v3.", evidenceId: "evt_9d27b4" },
    { id: "evt_7a1c35", action: "rolled_back", actor: "Jon Park", at: "2026-10-12T14:10:00Z", version: "v3", summary: "Rolled back v3 to v2. Reason: automated paging opened duplicate incidents.", evidenceId: "evt_7a1c35" },
    { id: "evt_3c8e1a", action: "promoted", actor: "Mira Chen", at: "2026-10-06T09:16:00Z", version: "v3", summary: "Promoted v3 to live.", evidenceId: "evt_3c8e1a" },
    { id: "evt_8b40d2", action: "promoted", actor: "Jon Park", at: "2026-09-22T15:42:00Z", version: "v2", summary: "Promoted v2 to live.", evidenceId: "evt_8b40d2" },
    { id: "evt_e2f7a6", action: "promoted", actor: "Mira Chen", at: "2026-09-12T11:12:00Z", version: "v1", summary: "Promoted v1 to live.", evidenceId: "evt_e2f7a6" },
  ],
}

export const directives: Directive[] = [supportTriage, billingAssistant, onboardingGuide, incidentResponder]

export function getDirectivePreview(id: string): Directive | null {
  return directives.find((directive) => directive.id === id) ?? null
}

export function directiveById(id: string): Directive | null {
  return getDirectivePreview(id)
}

export function directiveVersion(directive: Directive, version: string): DirectiveVersion | null {
  return directive.versions.find((entry) => entry.version === version) ?? null
}

export function directiveLive(directive: Directive): DirectiveVersion | null {
  return directive.versions.find((version) => version.state === "live") ?? null
}

export function directiveCandidate(directive: Directive): DirectiveVersion | null {
  return directive.versions.find((version) => version.state === "candidate") ?? null
}

export function directiveHasState(directive: Directive, state: DirectiveStateFilter): boolean {
  if (state === "all") return true
  return directive.versions.some((version) => version.state === state)
}

/** The rollback target is the version that was live before the current live version. */
export function directiveRollbackTarget(directive: Directive): DirectiveVersion | null {
  const live = directiveLive(directive)
  if (!live) return null
  const index = directive.versions.findIndex((version) => version.version === live.version)
  if (index < 0) return null
  return directive.versions.slice(index + 1).find((version) => version.state === "superseded" || version.state === "rolled_back") ?? null
}

export function directiveVersionDiff(directive: Directive, version: DirectiveVersion): { sections: SectionDiff[]; summary: DiffSummary } {
  const index = directive.versions.findIndex((entry) => entry.version === version.version)
  const previous = index >= 0 ? directive.versions[index + 1] : undefined
  const sections = diffDirectiveSections(previous?.sections ?? [], version.sections)
  return { sections, summary: diffSummary(sections) }
}

export function directiveDiff(directive: Directive, from: string, to: string): { sections: SectionDiff[]; summary: DiffSummary } {
  const fromVersion = directiveVersion(directive, from)
  const toVersion = directiveVersion(directive, to)
  const sections = diffDirectiveSections(fromVersion?.sections ?? [], toVersion?.sections ?? [])
  return { sections, summary: diffSummary(sections) }
}

export type DirectiveCheckSummary = {
  total: number
  passed: number
  failed: number
  pending: number
  skipped: number
  notConfigured: number
  label: string
  tone: "success" | "warning" | "destructive" | "neutral"
}

export function directiveCheckSummary(version: DirectiveVersion | null): DirectiveCheckSummary {
  if (!version || version.checks.length === 0) {
    return { total: 0, passed: 0, failed: 0, pending: 0, skipped: 0, notConfigured: 1, label: "Not configured", tone: "neutral" }
  }
  const count = (state: DirectiveCheckState): number => version.checks.filter((check) => check.state === state).length
  const passed = count("passed")
  const failed = count("failed")
  const pending = count("pending")
  const skipped = count("skipped")
  const notConfigured = count("not_configured")
  const tone = failed > 0 ? "destructive" : pending > 0 ? "warning" : passed === version.checks.length ? "success" : "neutral"
  return {
    total: version.checks.length,
    passed,
    failed,
    pending,
    skipped,
    notConfigured,
    label: `${passed}/${version.checks.length} passed`,
    tone,
  }
}

export type DirectiveApprovalState = {
  required: number
  approved: number
  waiting: number
  eligible: string[]
  authorExcluded: boolean
  waitingSince: string
  waitingLabel: string
  state: "approved" | "waiting" | "blocked" | "none"
}

export function directiveApprovalState(version: DirectiveVersion | null): DirectiveApprovalState {
  if (!version || version.approvalsRequired === 0) {
    return {
      required: 0,
      approved: 0,
      waiting: 0,
      eligible: [],
      authorExcluded: false,
      waitingSince: version?.createdAt ?? "",
      waitingLabel: "—",
      state: "none",
    }
  }
  const approved = version.approvals.filter((approval) => approval.decision === "approved").length
  const blocked = version.checks.some((check) => check.state === "failed")
  const eligible = version.eligibleApprovers.filter((actor) => actor !== version.author)
  return {
    required: version.approvalsRequired,
    approved,
    waiting: Math.max(0, version.approvalsRequired - approved),
    eligible,
    authorExcluded: eligible.length !== version.eligibleApprovers.length,
    waitingSince: version.createdAt,
    waitingLabel: formatGovernWait(version.createdAt),
    state: blocked ? "blocked" : approved >= version.approvalsRequired ? "approved" : "waiting",
  }
}

export type DirectiveBanner = {
  tone: "critical" | "warning" | "info"
  text: string
  detail: string
  tab: DirectiveTab
  action: string
}

export function directiveBanner(directive: Directive): DirectiveBanner | null {
  const candidate = directiveCandidate(directive)
  if (candidate) {
    const checks = directiveCheckSummary(candidate)
    if (checks.failed > 0) {
      const names = candidate.checks.filter((check) => check.state === "failed").map((check) => check.name).join(", ")
      return {
        tone: "critical",
        text: `${candidate.version} failed ${checks.failed} check${checks.failed === 1 ? "" : "s"}: ${names}. It cannot be promoted.`,
        detail: "Blocked",
        tab: "promotion",
        action: "See checks",
      }
    }
    const approval = directiveApprovalState(candidate)
    if (approval.waiting > 0) {
      return {
        tone: "warning",
        text: `${candidate.version} is waiting for ${approval.waiting} approval${approval.waiting === 1 ? "" : "s"}. ${candidate.author} wrote it, so someone else must approve.`,
        detail: `Waiting ${approval.waitingLabel}`,
        tab: "promotion",
        action: "Approval",
      }
    }
    return {
      tone: "info",
      text: `${candidate.version} has every check and approval. It is ready to promote.`,
      detail: "Ready",
      tab: "promotion",
      action: "Promotion",
    }
  }

  const live = directiveLive(directive)
  if (!live) {
    return {
      tone: "info",
      text: "No version is live. A draft must pass checks and approval before it can serve traffic.",
      detail: "No live version",
      tab: "versions",
      action: "Versions",
    }
  }
  return {
    tone: "info",
    text: `${live.version} is live${live.liveFrom ? ` since ${live.liveFrom.slice(0, 10)}` : ""}. No candidate is open.`,
    detail: "No candidate",
    tab: "overview",
    action: "Overview",
  }
}

export function directiveAuditEvents(directive: Directive): DirectiveEvent[] {
  return [...directive.events].sort((left, right) => Date.parse(right.at) - Date.parse(left.at))
}

/** One edge per row: a failed check outranks a version that is merely waiting. */
export function directiveRowEdge(directive: Directive): "warning" | "critical" | null {
  const candidate = directiveCandidate(directive)
  if (candidate) {
    if (directiveCheckSummary(candidate).failed > 0) return "critical"
    if (directiveApprovalState(candidate).state === "waiting") return "warning"
  }
  return null
}

/** The state an operator should read first: an open candidate, otherwise the live version. */
export function directivePrimaryState(directive: Directive): DirectiveState {
  return directiveCandidate(directive)?.state ?? directiveLive(directive)?.state ?? directive.versions[0]?.state ?? "draft"
}

/** Checks describe the candidate when one is open, otherwise the live version. */
export function directiveCheckTarget(directive: Directive): DirectiveVersion | null {
  return directiveCandidate(directive) ?? directiveLive(directive)
}

export function directiveLastChange(directive: Directive): { at: string; actor: string } | null {
  const latest = directive.versions[0]
  return latest ? { at: latest.createdAt, actor: latest.author } : null
}

export type DirectiveListStats = {
  awaiting: number
  oldestWaiting: string | null
  changedLast7Days: number
  rollbacksLast30Days: number
  failingChecks: number
}

export function directiveListStats(): DirectiveListStats {
  const candidates = directives.flatMap((directive) =>
    directive.versions.filter((version) => version.state === "candidate").map((version) => ({ directive, version })),
  )
  const awaiting = candidates.filter(({ version }) => {
    const approval = directiveApprovalState(version)
    return approval.state === "waiting"
  })
  const oldestWaiting = awaiting
    .map(({ version }) => version.createdAt)
    .sort((left, right) => Date.parse(left) - Date.parse(right))[0] ?? null
  const sevenDaysAgo = GOVERN_NOW - 7 * 24 * 60 * 60 * 1000
  const changedLast7Days = directives.reduce(
    (count, directive) =>
      count +
      directive.versions.filter(
        (version) => version.liveFrom !== null && Date.parse(version.liveFrom) >= sevenDaysAgo && version.liveFrom !== null,
      ).length,
    0,
  )
  const thirtyDaysAgo = GOVERN_NOW - 30 * 24 * 60 * 60 * 1000
  const rollbacksLast30Days = directives.reduce(
    (count, directive) =>
      count + directive.events.filter((event) => event.action === "rolled_back" && Date.parse(event.at) >= thirtyDaysAgo).length,
    0,
  )
  return {
    awaiting: awaiting.length,
    oldestWaiting,
    changedLast7Days,
    rollbacksLast30Days,
    failingChecks: candidates.filter(({ version }) => version.checks.some((check) => check.state === "failed")).length,
  }
}

export type DirectiveAttention = {
  id: string
  directiveId: string
  directiveName: string
  severity: "critical" | "warning" | "info"
  title: string
  detail: string
  at: string | null
  tab: DirectiveTab
}

export function directiveAttentionItems(): DirectiveAttention[] {
  const items: DirectiveAttention[] = []
  for (const directive of directives) {
    const candidate = directiveCandidate(directive)
    if (candidate) {
      const checks = directiveCheckSummary(candidate)
      if (checks.failed > 0) {
        items.push({
          id: `${directive.id}:check`,
          directiveId: directive.id,
          directiveName: directive.name,
          severity: "critical",
          title: `${candidate.version} failed ${checks.failed} check`,
          detail: candidate.checks.find((check) => check.state === "failed")?.name ?? "Promotion check",
          at: candidate.checks.find((check) => check.state === "failed")?.at ?? candidate.createdAt,
          tab: "promotion",
        })
        continue
      }
      const approval = directiveApprovalState(candidate)
      if (approval.state === "waiting") {
        items.push({
          id: `${directive.id}:approval`,
          directiveId: directive.id,
          directiveName: directive.name,
          severity: "warning",
          title: `${candidate.version} waiting for ${approval.waiting} approval${approval.waiting === 1 ? "" : "s"}`,
          detail: `${candidate.author} is the author`,
          at: candidate.createdAt,
          tab: "promotion",
        })
      }
    }
    const live = directiveLive(directive)
    if (live && !directiveRollbackTarget(directive)) {
      items.push({
        id: `${directive.id}:rollback`,
        directiveId: directive.id,
        directiveName: directive.name,
        severity: "info",
        title: "No rollback target",
        detail: `${live.version} is the first live version`,
        at: live.liveFrom,
        tab: "versions",
      })
    }
  }
  const rank = { critical: 0, warning: 1, info: 2 } as const
  return items.sort((left, right) => rank[left.severity] - rank[right.severity] || (right.at ? Date.parse(right.at) : 0) - (left.at ? Date.parse(left.at) : 0))
}

function matchesSearch(directive: Directive, search: string): boolean {
  if (!search) return true
  const haystack = [
    directive.name,
    directive.id,
    directive.description,
    directive.scope.org,
    directive.scope.workspace,
    directive.scope.area,
    ...directive.agents.map((agent) => agent.name),
    ...directive.versions.flatMap((version) => [version.version, version.summary ?? "", version.author]),
  ]
    .join(" ")
    .toLowerCase()
  return search
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => haystack.includes(term))
}

export function filterDirectives(
  source: Directive[],
  filter: { search: string; agent: string; state: DirectiveStateFilter },
): Directive[] {
  return source.filter(
    (directive) =>
      matchesSearch(directive, filter.search.trim()) &&
      (!filter.agent || filter.agent === "all" || directive.agents.some((agent) => agent.id === filter.agent)) &&
      directiveHasState(directive, filter.state),
  )
}

export function sortDirectives(source: Directive[], sort: DirectiveSortKey): Directive[] {
  return [...source].sort((left, right) => {
    if (sort === "name") return left.name.localeCompare(right.name)
    if (sort === "change") {
      return (Date.parse(right.versions[0]?.createdAt ?? "1970-01-01") || 0) - (Date.parse(left.versions[0]?.createdAt ?? "1970-01-01") || 0)
    }
    const leftLive = directiveLive(left)?.liveFrom ?? ""
    const rightLive = directiveLive(right)?.liveFrom ?? ""
    return (Date.parse(rightLive) || 0) - (Date.parse(leftLive) || 0)
  })
}

export function directiveAgentOptions(): { id: string; name: string; count: number }[] {
  const map = new Map<string, { id: string; name: string; count: number }>()
  for (const directive of directives) {
    for (const agent of directive.agents) {
      const entry = map.get(agent.id) ?? { id: agent.id, name: agent.name, count: 0 }
      entry.count += 1
      map.set(agent.id, entry)
    }
  }
  return [...map.values()].sort((left, right) => left.name.localeCompare(right.name))
}

export function directiveEventHref(event: DirectiveEvent): string {
  return `/audit?event=${encodeURIComponent(event.id)}`
}
