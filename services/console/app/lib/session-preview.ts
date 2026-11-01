import type { MemoryCategory } from "./memory-preview"

export type SessionFocus = "trace" | "memories" | "directive" | "policy" | "drift" | "privacy"

export type SessionSpanKind = "internal" | "retrieval" | "tool" | "llm" | "policy"

export type PreviewSession = {
  id: string
  title: string
  tier: "T1" | "T2" | "T3"
  agent: string
  env: "production" | "staging" | "development"
  first: string
  last: string
  turns: number
  duration: string
  outcome: "succeeded" | "denied" | "error"
  coverage: string
  error: string
  cost: string
  usage: string
}

export type SessionMemory = {
  id: string
  label: string
  fact: string
  category: MemoryCategory
  scope: string
  source: string
  similarity: number
  retrievedAt: string
  why: string
  usedInResponse: boolean
}

export type SessionDirectiveVersion = {
  version: string
  date: string
  current: boolean
  href: string | null
}

export type SessionDirective = {
  id: string
  name: string
  version: string
  scope: string
  hash: string
  loadedMs: number
  excerpt: string
  change: string
  whyApplied: string
  previousVersion: string
  publishedAt: string
  resolvedFor: string
  pinnedAtOffsetMs: number
  versions: SessionDirectiveVersion[]
}

export type SessionPolicyCheck = {
  label: string
  result: "pass" | "fail" | "not_run"
  detail: string
  decisive?: boolean
}

export type SessionPolicyThreshold = {
  value: number
  limit: number
  valueLabel: string
  limitLabel: string
}

export type SessionPolicyPermission = {
  tone: "allow" | "deny" | "approval"
  label: string
}

export type SessionPolicy = {
  id: string
  decision: "allow" | "deny" | "require_approval"
  scope: string
  action: string
  rule: string
  approval: string | null
  permits: string
  budget: string
  budgetDetail: string
  checks: SessionPolicyCheck[]
  threshold: SessionPolicyThreshold | null
  permissions: SessionPolicyPermission[]
  restrictions: string[]
  evaluatedInMs: number
}

export type SessionDrift = {
  id: string
  label: string
  severity: "advisory" | "warning" | "critical"
  status: "open" | "acknowledged" | "resolved"
  baseline: string
  detected: string
  sample: string
  detail: string
  uncertainty: string
  affected: string
  signal: string
  metric: string
  measured: number
  threshold: number
  evaluator: string
  checkedAtOffsetMs: number
  scope: string
}

export type SessionDriftCheck = {
  state: "clean" | "not_checked"
  evaluator: string | null
  checkedAtOffsetMs: number | null
  metric: string | null
  measured: number | null
  threshold: number | null
  detail: string | null
}

export type SessionToolCall = {
  name: string
  status: "ok" | "error" | "skipped"
  durationMs: number
  summary: string
  spanId: string | null
  args: Record<string, unknown>
  output: unknown
}

export type SessionCaptureMode = "metadata" | "redacted" | "off"

export type SessionCompleteness =
  | "complete"
  | "partial"
  | "sampled"
  | "late"
  | "redacted"
  | "expired"
  | "deleted"
  | "simulated"

export type SessionPiiFinding = {
  entity: string
  score: number
  occurrences: number
  action: "redacted" | "retained" | "quarantined"
}

export type SessionPrivacy = {
  captureMode: SessionCaptureMode
  completeness: SessionCompleteness
  redactionClass: "metadata" | "redacted"
  redactionProofVersion: string
  droppedFields: string[]
  pii: {
    detected: boolean
    redacted: boolean
    threshold: number
    findings: SessionPiiFinding[]
  }
  note: string
}

export type SessionSpan = {
  id: string
  label: string
  kind: SessionSpanKind
  offsetMs: number
  durationMs: number
  status: "ok" | "error"
  parentId: string | null
  /** One-line result rendered in the transcript step list. */
  summary: string
  /** Structured span payload rendered beside the span in the inspector. */
  attributes: Record<string, unknown>
}

export type SessionRound = {
  id: string
  index: number
  startedAt: string
  userText: string
  assistantText: string
  reasoning: string
  traceId: string
  runId: string
  model: string
  latencyMs: number
  tokensIn: number
  tokensOut: number
  cost: string
  outcome: "succeeded" | "denied" | "error"
  error: string | null
  memories: SessionMemory[]
  directive: SessionDirective
  policy: SessionPolicy
  drift: SessionDrift | null
  driftCheck: SessionDriftCheck | null
  toolCalls: SessionToolCall[]
  spans: SessionSpan[]
  privacy?: SessionPrivacy
}

export const previewSessions: PreviewSession[] = [
  { id: "ses_2481f0a2", title: "Refund policy escalation", tier: "T1", agent: "Support triage", env: "production", first: "13:09:24", last: "13:09:38", turns: 4, duration: "14.05s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.09021", usage: "2,966 in · 441 out" },
  { id: "ses_6f9a71c4", title: "Invoice export troubleshooting", tier: "T2", agent: "Billing analyst", env: "production", first: "13:06:10", last: "13:07:25", turns: 7, duration: "1m 15s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.07039", usage: "56,977 → 2,558" },
  { id: "ses_4c11e7f2", title: "Workspace onboarding plan", tier: "T1", agent: "Onboarding guide", env: "production", first: "13:05:58", last: "13:08:22", turns: 9, duration: "2m 24s", outcome: "succeeded", coverage: "3 / 3", error: "—", cost: "$0.03859", usage: "58,900 → 1,401" },
  { id: "ses_18bd3e09", title: "PII redaction review", tier: "T1", agent: "Policy reviewer", env: "staging", first: "13:05:51", last: "13:06:11", turns: 3, duration: "20.00s", outcome: "denied", coverage: "1 / 1", error: "policy_denied", cost: "$0.0381", usage: "31,766 → 884" },
  { id: "ses_cf2f18b9", title: "Retention policy question", tier: "T2", agent: "Knowledge curator", env: "production", first: "13:05:34", last: "13:05:51", turns: 3, duration: "17.00s", outcome: "succeeded", coverage: "1 / 1", error: "—", cost: "$0.01945", usage: "7,247 → 1,107" },
  { id: "ses_075ef6a2", title: "Billing export retry semantics", tier: "T2", agent: "Billing analyst", env: "production", first: "13:05:12", last: "13:05:33", turns: 4, duration: "21.00s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.06671", usage: "396 → 55" },
  { id: "ses_6b6c5cf3", title: "Support hours clarification", tier: "T3", agent: "Support triage", env: "production", first: "13:05:01", last: "13:05:11", turns: 2, duration: "10.00s", outcome: "succeeded", coverage: "1 / 1", error: "—", cost: "$0.01564", usage: "914 → 126" },
  { id: "ses_05b318a9", title: "Audit event interpretation", tier: "T2", agent: "Compliance auditor", env: "production", first: "12:05:20", last: "12:05:41", turns: 3, duration: "21.00s", outcome: "succeeded", coverage: "1 / 1", error: "—", cost: "$0.040812", usage: "32,512 → 838" },
  { id: "ses_60c408e0", title: "Provider failover verification", tier: "T1", agent: "Escalation router", env: "staging", first: "11:49:20", last: "11:49:48", turns: 5, duration: "28.00s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.046181", usage: "32,711 → 1,356" },
  { id: "ses_d2f79fa2", title: "Memory conflict resolution", tier: "T1", agent: "Knowledge curator", env: "production", first: "11:18:29", last: "11:18:51", turns: 4, duration: "22.00s", outcome: "succeeded", coverage: "3 / 3", error: "—", cost: "$0.01759", usage: "7,218 → 1,813" },
  { id: "ses_1d8c2ee4", title: "Deploy freeze clarification", tier: "T3", agent: "Onboarding guide", env: "development", first: "11:03:21", last: "11:03:51", turns: 3, duration: "30.00s", outcome: "error", coverage: "1 / 1", error: "upstream_timeout", cost: "$0.034221", usage: "23,233 → 896" },
  { id: "ses_7b30d4e8", title: "Token budget review", tier: "T2", agent: "Billing analyst", env: "production", first: "10:58:11", last: "10:58:36", turns: 4, duration: "25.00s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.036523", usage: "23,458 → 1,000" },
  { id: "ses_b14ec3a5", title: "Key rotation checklist", tier: "T2", agent: "Compliance auditor", env: "production", first: "10:52:44", last: "10:53:00", turns: 3, duration: "16.00s", outcome: "succeeded", coverage: "1 / 1", error: "—", cost: "$0.01382", usage: "892 → 116" },
  { id: "ses_c46a8f3d", title: "Latency SLO investigation", tier: "T1", agent: "Support triage", env: "production", first: "10:44:03", last: "10:44:34", turns: 6, duration: "31.00s", outcome: "error", coverage: "2 / 3", error: "span_gap", cost: "$0.016256", usage: "7,248 → 878" },
  { id: "ses_1a125b6f", title: "Duplicate charge audit", tier: "T1", agent: "Billing analyst", env: "production", first: "10:41:39", last: "10:41:58", turns: 3, duration: "19.00s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.043243", usage: "33,766 → 1,054" },
  { id: "ses_1273b9e9", title: "Evidence coverage check", tier: "T3", agent: "Policy reviewer", env: "staging", first: "10:34:44", last: "10:35:11", turns: 3, duration: "27.00s", outcome: "denied", coverage: "1 / 1", error: "policy_denied", cost: "$0.01391", usage: "801 → 118" },
  { id: "ses_5a91e2c8", title: "Refund approval routing", tier: "T2", agent: "Support triage", env: "production", first: "10:18:25", last: "10:18:48", turns: 4, duration: "23.00s", outcome: "succeeded", coverage: "2 / 2", error: "—", cost: "$0.020162", usage: "7,213 → 1,273" },
  { id: "ses_9c02a741", title: "Tenant isolation rehearsal", tier: "T1", agent: "Fraud sentinel", env: "staging", first: "09:33:23", last: "09:33:55", turns: 7, duration: "32.00s", outcome: "succeeded", coverage: "3 / 3", error: "—", cost: "$0.08197", usage: "38,828 → 931" },
]

const refundMemories: SessionMemory[] = [
  {
    id: "mem_77b031",
    label: "Duplicate-charge refund policy",
    fact: "Refund the later settled charge and keep the original idempotency key for retries.",
    category: "factual",
    scope: "Session",
    source: "Session memory",
    similarity: 0.92,
    retrievedAt: "6m ago",
    why: "Matched the invoice ID and the duplicate-settlement clause for this customer.",
    usedInResponse: true,
  },
  {
    id: "mem_6f9a71c4",
    label: "Email updates for refund status",
    fact: "This customer prefers email updates for refund status changes.",
    category: "preference",
    scope: "Session",
    source: "Session memory",
    similarity: 0.71,
    retrievedAt: "6m ago",
    why: "Retrieved while drafting the reply. It did not change the refund decision.",
    usedInResponse: false,
  },
]

const retryMemory: SessionMemory = {
  id: "mem_cf2f18b9",
  label: "Provider retry budget",
  fact: "Provider retry budget is three attempts with exponential backoff and jitter.",
  category: "factual",
  scope: "Organization",
  source: "Organization memory",
  similarity: 0.88,
  retrievedAt: "5m ago",
  why: "Matched the provider retry marker on the second settlement.",
  usedInResponse: true,
}

const supportDirective: SessionDirective = {
  id: "support-v8",
  name: "Support refund policy",
  version: "v8",
  scope: "support.refund",
  hash: "sha256:9f2a…c81e",
  loadedMs: 4.2,
  excerpt:
    "Duplicate settlements caused by a provider retry are refundable in full when both charges share invoice_id and settle within 24 hours.",
  change:
    "v8 added provider-retry settlements and required a neutral customer explanation instead of blaming a system error.",
  whyApplied: "Resolved for org_demo_42 and pinned to this turn before generation.",
  previousVersion: "v7 · Oct 20",
  publishedAt: "22 Oct 2026",
  resolvedFor: "org_demo_42",
  pinnedAtOffsetMs: 0,
  versions: [
    { version: "v7", date: "20 Oct 2026", current: false, href: "/directives?directive=support-v8&version=v7" },
    { version: "v8", date: "22 Oct 2026", current: true, href: "/directives?directive=support-v8" },
  ],
}

const supportPolicy: SessionPolicy = {
  id: "agent.support.v3",
  decision: "allow",
  scope: "support.refund",
  action: "refund.preview",
  rule: "Duplicate-charge refunds below $250 may proceed without escalation.",
  approval: "Mutations require an explicit approval step.",
  permits:
    "The response may explain the refund and prepare a reply. It cannot move money or write to the ledger; any mutation still needs explicit approval outside this preview.",
  budget: "81% committed",
  budgetDetail: "$2,025 of the $2,500 daily refund-review budget",
  checks: [
    { label: "Refund window", result: "pass", detail: "Charges settled six minutes apart, inside the 24-hour window.", decisive: false },
    { label: "Finance threshold", result: "pass", detail: "$84.00 refund is below the $250 escalation threshold.", decisive: true },
    { label: "Read-only action", result: "pass", detail: "Preview only. No ledger mutation was attempted.", decisive: false },
  ],
  threshold: { value: 84, limit: 250, valueLabel: "$84.00", limitLabel: "$250" },
  permissions: [
    { tone: "allow", label: "Explain the refund and prepare a reply" },
    { tone: "deny", label: "Move money or write to the ledger" },
    { tone: "approval", label: "Any mutation needs explicit approval outside this preview" },
  ],
  restrictions: ["Mutations require an explicit approval step."],
  evaluatedInMs: 19,
}

const refundDrift: SessionDrift = {
  id: "drift_retry_refund_wording",
  label: "Refund wording drift",
  severity: "advisory",
  status: "open",
  baseline: "support-v7 · established Oct 20",
  detected: "Oct 27 · 12:40",
  sample: "18 replies over 7 days",
  detail:
    "Reply wording differs from the policy-backed answer in Turn 1: it says “reverse the charge” where policy requires a credit note.",
  uncertainty: "Low harm signal. The sample is small and does not isolate this agent.",
  affected: "Turns 3 and 4",
  signal: "3 wording deviations in 7 days · advisory threshold met",
  metric: "Wording deviation rate",
  measured: 0.18,
  threshold: 0.15,
  evaluator: "drift.evaluator.v2",
  checkedAtOffsetMs: 288,
  scope: "This turn only",
}

function span(
  id: string,
  label: string,
  kind: SessionSpanKind,
  offsetMs: number,
  durationMs: number,
  summary: string,
  attributes: Record<string, unknown> = {},
  parentId: string | null = null,
): SessionSpan {
  return { id, label, kind, offsetMs, durationMs, status: "ok", parentId, summary, attributes }
}

function refundRound(round: Omit<SessionRound, "id" | "directive" | "policy"> & { id?: string }): SessionRound {
  return {
    ...round,
    id: round.id ?? `round-${round.index}`,
    directive: supportDirective,
    policy: supportPolicy,
  }
}

const refundThread: SessionRound[] = [
  refundRound({
    index: 1,
    startedAt: "13:09:24",
    userText: "A customer was charged twice for invoice INV-2481. Can we refund the duplicate charge?",
    assistantText:
      "Yes. Two settled charges for the same invoice are treated as a duplicate settlement, and the second charge is refundable in full. I checked the charge pair and the current refund rule before answering.",
    reasoning:
      "support-refund v8 allows a duplicate-charge refund when both charges share invoice_id, customer_id, and a settlement window under 24 hours. The two charges differ by six minutes.",
    traceId: "trc_9f2a7c41",
    runId: "run_01J9Z4K2M8Q1V6R3",
    model: "gpt-4.1",
    latencyMs: 320,
    tokensIn: 892,
    tokensOut: 129,
    cost: "$0.03197",
    outcome: "succeeded",
    error: null,
    memories: refundMemories,
    drift: null,
    driftCheck: {
      state: "not_checked",
      evaluator: null,
      checkedAtOffsetMs: null,
      metric: null,
      measured: null,
      threshold: null,
      detail: null,
    },
    toolCalls: [
      {
        name: "lookup_charge",
        status: "ok",
        durationMs: 42,
        summary: "Returned two settled charges for INV-2481.",
        spanId: "span-t1-lookup",
        args: { invoice_id: "INV-2481", include_settlements: true },
        output: {
          charges: [
            { charge_id: "ch_8f31", amount: 84, currency: "USD", settled_at: "2026-10-27T13:03:12Z" },
            { charge_id: "ch_8f32", amount: 84, currency: "USD", settled_at: "2026-10-27T13:09:18Z" },
          ],
          duplicate: true,
        },
      },
      {
        name: "refund.preview",
        status: "ok",
        durationMs: 18,
        summary: "Refundable amount $84.00; no ledger write.",
        spanId: "span-t1-refund-preview",
        args: { charge_id: "ch_8f32", mode: "preview" },
        output: { refundable: 84, currency: "USD", ledger_write: false, approval_required: false },
      },
    ],
    spans: [
      span("span-t1-context", "context.assemble", "internal", 0, 34, "Loaded directive support-v8 and 2 memory candidates.", {
        input: { directive: "support-v8", budget_tokens: 2048 },
        output: { memories: 2, directive_tokens: 96 },
      }),
      span(
        "span-t1-memory",
        "memory.retrieve",
        "retrieval",
        34,
        61,
        "2 memories · 1 used in reply",
        {
          input: { query: "duplicate charge refund INV-2481", limit: 5 },
          output: { retrieved: 2, included: 1, ids: ["mem_77b031", "mem_6f9a71c4"] },
        },
        "span-t1-context",
      ),
      span("span-t1-lookup", "tool.lookup_charge", "tool", 95, 42, "Returned two settled charges for INV-2481.", {
        input: { invoice_id: "INV-2481", include_settlements: true },
        output: { duplicate: true, charges: 2 },
      }),
      span("span-t1-refund-preview", "tool.refund.preview", "tool", 137, 18, "Refundable amount $84.00; no ledger write.", {
        input: { charge_id: "ch_8f32", mode: "preview" },
        output: { refundable: 84, currency: "USD", ledger_write: false, approval_required: false },
      }),
      span("span-t1-provider", "provider.request", "llm", 155, 164, "gpt-4.1 · 892 in · 129 out", {
        input: { model: "gpt-4.1", messages: 2, temperature: 0.2 },
        output: { finish_reason: "stop", tokens_out: 129 },
      }),
      span("span-t1-policy", "policy.check", "policy", 301, 19, "allow · support-v8", {
        input: { action: "refund.preview", amount_usd: 84 },
        output: { decision: "allow", checks_passed: 3, checks_failed: 0 },
      }),
    ],
  }),
  refundRound({
    index: 2,
    startedAt: "13:09:29",
    userText: "The second charge came from a provider retry. Does that change the answer?",
    assistantText:
      "It does not change the refund decision, but it changes the evidence. A retry-created duplicate is still refundable; the reply should name the retry so support can trace it.",
    reasoning:
      "The retry marker is present on the second charge. Policy v8 explicitly includes provider retries. The wording drift advisory suggests avoiding the phrase “system error” in customer replies.",
    traceId: "trc_4b18e2d7",
    runId: "run_01J9Z4M5F0C8N2W7",
    model: "gpt-4.1",
    latencyMs: 260,
    tokensIn: 612,
    tokensOut: 96,
    cost: "$0.01842",
    outcome: "succeeded",
    error: null,
    memories: [...refundMemories, retryMemory],
    drift: null,
    driftCheck: {
      state: "clean",
      evaluator: "drift.evaluator.v2",
      checkedAtOffsetMs: 260,
      metric: "Wording deviation rate",
      measured: 0.06,
      threshold: 0.15,
      detail: "No wording deviation found against the support-v8 baseline.",
    },
    toolCalls: [
      {
        name: "lookup_provider_retry",
        status: "ok",
        durationMs: 37,
        summary: "Retry marker confirmed on the second settlement.",
        spanId: "span-t2-retry",
        args: { charge_id: "ch_8f32" },
        output: { retry_marker: true, attempts: 2, provider: "stripe" },
      },
    ],
    spans: [
      span("span-t2-context", "context.assemble", "internal", 0, 29, "Loaded directive support-v8 and 3 memory candidates.", {
        input: { directive: "support-v8", budget_tokens: 2048 },
        output: { memories: 3 },
      }),
      span(
        "span-t2-memory",
        "memory.retrieve",
        "retrieval",
        29,
        48,
        "3 memories · 2 used in reply",
        {
          input: { query: "provider retry duplicate charge", limit: 5 },
          output: { retrieved: 3, included: 2, ids: ["mem_77b031", "mem_6f9a71c4", "mem_cf2f18b9"] },
        },
        "span-t2-context",
      ),
      span("span-t2-retry", "tool.lookup_provider_retry", "tool", 77, 37, "Retry marker confirmed on the second settlement.", {
        input: { charge_id: "ch_8f32" },
        output: { retry_marker: true, attempts: 2, provider: "stripe" },
      }),
      span("span-t2-provider", "provider.request", "llm", 114, 134, "gpt-4.1 · 612 in · 96 out", {
        input: { model: "gpt-4.1", messages: 2, temperature: 0.2 },
        output: { finish_reason: "stop", tokens_out: 96 },
      }),
      span("span-t2-policy", "policy.check", "policy", 248, 12, "allow · support-v8", {
        input: { action: "refund.preview", amount_usd: 84 },
        output: { decision: "allow", checks_passed: 3, checks_failed: 0 },
      }),
    ],
  }),
  refundRound({
    index: 3,
    startedAt: "13:09:33",
    userText: "The invoice was already exported to their ERP. Can we still refund it?",
    assistantText:
      "Yes. The refund is independent of the export. Issue a credit note and let the ERP sync reconcile it; do not reverse the original settlement.",
    reasoning:
      "Export state is not a policy gate. The drift baseline flagged wording around ERP credit notes, so the response uses the current clause and avoids “reverse the charge”.",
    traceId: "trc_7c02a9fe",
    runId: "run_01J9Z4P9T3H5B8X1",
    model: "gpt-4.1",
    latencyMs: 288,
    tokensIn: 704,
    tokensOut: 112,
    cost: "$0.02118",
    outcome: "succeeded",
    error: null,
    memories: refundMemories,
    drift: refundDrift,
    driftCheck: null,
    toolCalls: [
      {
        name: "check_erp_export",
        status: "ok",
        durationMs: 51,
        summary: "Invoice exported Oct 25; no credit note present.",
        spanId: "span-t3-export",
        args: { invoice_id: "INV-2481" },
        output: { exported: true, exported_at: "2026-10-25T09:14:00Z", credit_note: false },
      },
    ],
    spans: [
      span("span-t3-context", "context.assemble", "internal", 0, 31, "Loaded directive support-v8 and 2 memory candidates.", {
        input: { directive: "support-v8", budget_tokens: 2048 },
        output: { memories: 2 },
      }),
      span(
        "span-t3-memory",
        "memory.retrieve",
        "retrieval",
        31,
        55,
        "2 memories · 1 used in reply",
        {
          input: { query: "ERP export credit note duplicate refund", limit: 5 },
          output: { retrieved: 2, included: 1, ids: ["mem_77b031", "mem_6f9a71c4"] },
        },
        "span-t3-context",
      ),
      span("span-t3-export", "tool.check_erp_export", "tool", 86, 51, "Invoice exported Oct 25; no credit note present.", {
        input: { invoice_id: "INV-2481" },
        output: { exported: true, exported_at: "2026-10-25T09:14:00Z", credit_note: false },
      }),
      span("span-t3-provider", "provider.request", "llm", 137, 139, "gpt-4.1 · 704 in · 112 out", {
        input: { model: "gpt-4.1", messages: 2, temperature: 0.2 },
        output: { finish_reason: "stop", tokens_out: 112 },
      }),
      span("span-t3-policy", "policy.check", "policy", 276, 12, "allow · support-v8", {
        input: { action: "refund.preview", amount_usd: 84 },
        output: { decision: "allow", checks_passed: 3, checks_failed: 0 },
      }),
    ],
  }),
  refundRound({
    index: 4,
    startedAt: "13:09:36",
    userText: "Draft the customer reply and escalate only if finance must approve.",
    assistantText:
      "Draft ready. Finance approval is not required below $250, so I would not escalate. Send the reply with the refund reference and credit-note guidance.",
    reasoning:
      "The refund amount is $84.00, below the $250 finance threshold. Escalation is unnecessary. The draft avoids the drift phrase and names the provider retry.",
    traceId: "trc_2d88f510",
    runId: "run_01J9Z4R1K7D4M6Q9",
    model: "gpt-4.1",
    latencyMs: 312,
    tokensIn: 758,
    tokensOut: 104,
    cost: "$0.01864",
    outcome: "succeeded",
    error: null,
    memories: refundMemories,
    drift: refundDrift,
    driftCheck: null,
    toolCalls: [
      {
        name: "draft_reply",
        status: "ok",
        durationMs: 26,
        summary: "Reply drafted with refund reference and credit-note guidance.",
        spanId: "span-t4-draft",
        args: { tone: "neutral", include_credit_note: true },
        output: { draft_chars: 412, mentions_retry: true },
      },
      {
        name: "create_escalation",
        status: "skipped",
        durationMs: 0,
        summary: "Skipped: amount below the $250 finance threshold.",
        spanId: null,
        args: { reason: "finance_threshold", amount_usd: 84 },
        output: null,
      },
    ],
    spans: [
      span("span-t4-context", "context.assemble", "internal", 0, 33, "Loaded directive support-v8 and 2 memory candidates.", {
        input: { directive: "support-v8", budget_tokens: 2048 },
        output: { memories: 2 },
      }),
      span(
        "span-t4-memory",
        "memory.retrieve",
        "retrieval",
        33,
        52,
        "2 memories · 1 used in reply",
        {
          input: { query: "refund reply finance approval threshold", limit: 5 },
          output: { retrieved: 2, included: 1, ids: ["mem_77b031", "mem_6f9a71c4"] },
        },
        "span-t4-context",
      ),
      span("span-t4-provider", "provider.request", "llm", 85, 187, "gpt-4.1 · 758 in · 104 out", {
        input: { model: "gpt-4.1", messages: 2, temperature: 0.2 },
        output: { finish_reason: "stop", tokens_out: 104 },
      }),
      span("span-t4-draft", "tool.draft_reply", "tool", 272, 26, "Reply drafted with refund reference and credit-note guidance.", {
        input: { tone: "neutral", include_credit_note: true },
        output: { draft_chars: 412, mentions_retry: true },
      }),
      span("span-t4-policy", "policy.check", "policy", 298, 14, "allow · support-v8", {
        input: { action: "refund.preview", amount_usd: 84 },
        output: { decision: "allow", checks_passed: 3, checks_failed: 0 },
      }),
    ],
  }),
]

function numericUsage(value: string): { input: number; output: number } {
  const numbers = value.match(/\d[\d,]*/g)?.map((entry) => Number(entry.replaceAll(",", ""))) ?? []
  return { input: numbers[0] ?? 0, output: numbers[1] ?? 0 }
}

function numericCost(value: string): number {
  return Number.parseFloat(value.replace(/[^0-9.]/g, "")) || 0
}

const redactedSessionPrivacy: SessionPrivacy = {
  captureMode: "redacted",
  completeness: "redacted",
  redactionClass: "redacted",
  redactionProofVersion: "session-metadata-allowlist/v1",
  droppedFields: ["content", "prompt", "tools", "span.attributes", "span.error_code"],
  pii: {
    detected: true,
    redacted: true,
    threshold: 0.6,
    findings: [
      { entity: "CREDIT_CARD", score: 0.96, occurrences: 2, action: "redacted" },
      { entity: "PHONE_NUMBER", score: 0.81, occurrences: 1, action: "redacted" },
    ],
  },
  note: "Prompt, completion, tool payloads, and span attributes were removed before storage. The row remains readable as metadata, but the relay must not project it as if the content were complete.",
}

function genericThread(session: PreviewSession): SessionRound[] {
  const topic = session.title.toLowerCase()
  const baseTime = session.first
  const prefix = session.id.slice(4, 10)
  const failed = session.outcome === "error" || session.outcome === "denied"
  const errorMessage = session.outcome === "error" ? `Upstream provider timed out (${session.error}).` : null
  const usage = numericUsage(session.usage)
  const totalCost = numericCost(session.cost)
  const split = (ratio: number) => `$${(totalCost * ratio).toFixed(5)}`
  const rounds = [
    refundRound({
      index: 1,
      startedAt: baseTime,
      userText: `Can you walk me through the current ${topic} decision?`,
      assistantText: `I’ll ground the answer in the active directive, the retrieved memories, and the policy snapshot for ${session.agent}. The session record shows a ${session.outcome} outcome with ${session.coverage} evidence coverage.`,
      reasoning:
        "The response is generated from the illustrative session fixture. It shows how a real turn would expose context, evidence, and a trace without claiming live content.",
      traceId: `trc_${prefix}a1`,
      runId: `run_${prefix}a1`,
      model: "gpt-4.1",
      latencyMs: 284,
      tokensIn: Math.round(usage.input * 0.57),
      tokensOut: Math.round(usage.output * 0.57),
      cost: split(0.57),
      outcome: session.outcome,
      error: errorMessage,
      memories: refundMemories,
      drift: failed ? refundDrift : null,
      driftCheck: failed
        ? null
        : {
            state: "not_checked",
            evaluator: null,
            checkedAtOffsetMs: null,
            metric: null,
            measured: null,
            threshold: null,
            detail: null,
          },
      toolCalls: [
        {
          name: "retrieve_context",
          status: "ok",
          durationMs: 44,
          summary: "Loaded directive and memory candidates.",
          spanId: `span-${prefix}-a1-tool`,
          args: { limit: 5 },
          output: { directive: "support-v8", memories: 2 },
        },
      ],
      spans: [
        span(`span-${prefix}-a1-context`, "context.assemble", "internal", 0, 32, "Loaded directive and memory candidates.", {
          input: { directive: "support-v8" },
          output: { memories: 2 },
        }),
        span(
          `span-${prefix}-a1-memory`,
          "memory.retrieve",
          "retrieval",
          32,
          56,
          "2 memories · 1 used in reply",
          { input: { query: topic, limit: 5 }, output: { retrieved: 2, included: 1 } },
          `span-${prefix}-a1-context`,
        ),
        span(
          `span-${prefix}-a1-provider`,
          "provider.request",
          "llm",
          88,
          176,
          session.outcome === "error" ? "Upstream timeout" : "gpt-4.1 · 612 in · 118 out",
          {
            input: { model: "gpt-4.1" },
            output: session.outcome === "error" ? null : { finish_reason: "stop" },
            error: errorMessage,
          },
        ),
        span(`span-${prefix}-a1-policy`, "policy.check", "policy", 264, 14, "allow · support-v8", {
          input: { action: "refund.preview" },
          output: { decision: "allow" },
        }),
      ],
    }),
    refundRound({
      index: 2,
      startedAt: session.last,
      userText: `What evidence supports that ${topic} answer, and what should I check next?`,
      assistantText: `The answer is backed by ${session.coverage} coverage across the session. The right-side inspector keeps the trace, memories, directive version, policy decision, and any drift advisory together so the next check is explicit.`,
      reasoning:
        "This illustrative turn demonstrates the evidence drill-down pattern. Live session content is not connected, so no value in this preview is presented as observed tenant data.",
      traceId: `trc_${prefix}b2`,
      runId: `run_${prefix}b2`,
      model: "gpt-4.1",
      latencyMs: 248,
      tokensIn: usage.input - Math.round(usage.input * 0.57),
      tokensOut: usage.output - Math.round(usage.output * 0.57),
      cost: split(0.43),
      outcome: session.outcome,
      error: errorMessage,
      memories: [retryMemory, ...refundMemories.slice(0, 1)],
      drift: session.outcome === "denied" ? refundDrift : null,
      driftCheck:
        session.outcome === "denied"
          ? null
          : {
              state: "clean",
              evaluator: "drift.evaluator.v2",
              checkedAtOffsetMs: 248,
              metric: "Wording deviation rate",
              measured: 0.04,
              threshold: 0.15,
              detail: "No wording deviation found against the active baseline.",
            },
      toolCalls: [
        {
          name: "evidence.check",
          status: "ok",
          durationMs: 39,
          summary: "Verified coverage against the policy snapshot.",
          spanId: `span-${prefix}-b2-tool`,
          args: { coverage: session.coverage },
          output: { verified: true },
        },
      ],
      spans: [
        span(`span-${prefix}-b2-context`, "context.assemble", "internal", 0, 28, "Loaded directive and evidence candidates.", {
          input: { directive: "support-v8" },
          output: { memories: 2 },
        }),
        span(
          `span-${prefix}-b2-memory`,
          "memory.retrieve",
          "retrieval",
          28,
          47,
          "2 memories · 1 used in reply",
          { input: { query: `${topic} evidence`, limit: 5 }, output: { retrieved: 2, included: 1 } },
          `span-${prefix}-b2-context`,
        ),
        span(`span-${prefix}-b2-provider`, "provider.request", "llm", 75, 158, "gpt-4.1 · 548 in · 102 out", {
          input: { model: "gpt-4.1" },
          output: { finish_reason: "stop" },
        }),
        span(`span-${prefix}-b2-policy`, "policy.check", "policy", 233, 15, "allow · support-v8", {
          input: { action: "refund.preview" },
          output: { decision: "allow" },
        }),
      ],
    }),
  ]
  if (session.id === "ses_18bd3e09") {
    for (const round of rounds) round.privacy = redactedSessionPrivacy
  }
  return rounds
}

export function getSessionPreview(id: string): PreviewSession {
  return previewSessions.find((session) => session.id === id) ?? previewSessions[0]!
}

export function getSessionThread(session: PreviewSession): SessionRound[] {
  return session.id === "ses_2481f0a2" ? refundThread : genericThread(session)
}
