import type {
  ActionLedgerEntry,
  DirectiveDetail,
  DirectiveListItem,
  DirectiveVersion,
} from "./types"

const V3_CONTENT = `You are the Support Agent for enterprise refund requests.

## Escalation
When the customer requests tier-2 escalation or the case involves
regulatory risk, escalate immediately — do not attempt to resolve
independently.

## Refund window
Enterprise plans: 30-day refund window from invoice date.
Cite policy#refund-ent when stating the window.
`

const V2_CONTENT = `You are the Support Agent for enterprise refund requests.

## Refund window
Enterprise plans: 30-day refund window from invoice date.
Cite policy#refund-ent when stating the window.

Attempt to resolve independently before escalating.
`

const versionsSupport: DirectiveVersion[] = [
  {
    version: 3,
    status: "active",
    content_hash: "9f2a…c1",
    content_tokens: 128,
    content: V3_CONTENT,
    created_at: "2025-09-17T10:00:00.000Z",
    created_by: "jane@acme.com",
    promoted_at: "2025-09-18T14:02:00.000Z",
    promoted_by: "jane@acme.com",
    revoked_reason: null,
    regression_status: "passed",
    scenarios_passed: 47,
    scenarios_total: 47,
  },
  {
    version: 2,
    status: "deprecated",
    content_hash: "4e88…b2",
    content_tokens: 98,
    content: V2_CONTENT,
    created_at: "2025-08-01T09:00:00.000Z",
    created_by: "ops@acme.com",
    promoted_at: "2025-08-02T11:00:00.000Z",
    promoted_by: "ops@acme.com",
    revoked_reason: null,
    regression_status: "passed",
    scenarios_passed: 46,
    scenarios_total: 47,
  },
  {
    version: 1,
    status: "revoked",
    content_hash: "1a0c…d9",
    content_tokens: 84,
    content: "Legacy instructions (revoked).",
    created_at: "2025-06-01T08:00:00.000Z",
    created_by: "ops@acme.com",
    promoted_at: "2025-06-02T10:00:00.000Z",
    promoted_by: "ops@acme.com",
    revoked_reason: "Security vulnerability discovered in instructions",
    regression_status: "not_run",
    scenarios_passed: 0,
    scenarios_total: 0,
  },
]

const ledgerSupport: ActionLedgerEntry[] = [
  {
    id: "led_01",
    at: "2025-09-18T14:02:00.000Z",
    actor: "jane@acme.com",
    kind: "promote",
    summary: "promote v2→v3 gradual",
    before_version: 2,
    after_version: 3,
    idempotency_key: "promote:support-refund:v3",
    reason: "Escalation instructions + regression 47/47",
  },
  {
    id: "led_02",
    at: "2025-09-17T09:15:00.000Z",
    actor: "system",
    kind: "auto_rollback",
    summary: "auto-rollback guardrail breach (prior attempt)",
    before_version: 3,
    after_version: 2,
    idempotency_key: "abort:support-refund:2025-09-17",
    reason: "latency guardrail breached at 34% rollout",
  },
  {
    id: "led_03",
    at: "2025-09-15T11:40:00.000Z",
    actor: "ops@acme.com",
    kind: "revoke",
    summary: "revoke v1 MFA+2-approval",
    before_version: 1,
    after_version: null,
    idempotency_key: "revoke:support-refund:v1",
    reason: "Security vulnerability discovered in instructions",
  },
  {
    id: "led_04",
    at: "2025-09-17T10:05:00.000Z",
    actor: "jane@acme.com",
    kind: "submit_review",
    summary: "submit v3 for review",
    before_version: null,
    after_version: 3,
    idempotency_key: "review:support-refund:v3",
  },
]

export const DIRECTIVE_SUPPORT: DirectiveDetail = {
  directive_id: "dir_support_refund",
  name: "support-refund",
  agent: "Support Agent",
  org: "Acme Corp",
  status: "active",
  active_version: 3,
  regression_status: "passed",
  scenarios_passed: 47,
  scenarios_total: 47,
  last_promoted_by: "jane@acme.com",
  last_promoted_at: "2025-09-18T14:02:00.000Z",
  owner: "jane@acme.com",
  description:
    "Enterprise refund policy directive. Gradual rollout of v3 escalation instructions.",
  rollout: {
    strategy: "gradual",
    percentage: 10,
    stage: "pct_10",
    paused: false,
  },
  versions: versionsSupport,
  diff: {
    from_version: 2,
    to_version: 3,
    additions: 6,
    deletions: 1,
    token_delta: 30,
    hunks: [
      {
        header: "@@ -1,8 +1,14 @@",
        lines: [
          {
            op: " ",
            text: "You are the Support Agent for enterprise refund requests.",
          },
          { op: " ", text: "" },
          { op: "+", text: "## Escalation" },
          {
            op: "+",
            text: "When the customer requests tier-2 escalation or the case involves",
          },
          {
            op: "+",
            text: "regulatory risk, escalate immediately — do not attempt to resolve",
          },
          { op: "+", text: "independently." },
          { op: "+", text: "" },
          { op: " ", text: "## Refund window" },
          {
            op: " ",
            text: "Enterprise plans: 30-day refund window from invoice date.",
          },
          {
            op: " ",
            text: "Cite policy#refund-ent when stating the window.",
          },
          {
            op: "-",
            text: "Attempt to resolve independently before escalating.",
          },
        ],
      },
    ],
  },
  behavioral: {
    test_scenarios_run: 47,
    behavior_changed: 3,
    behavior_unchanged: 44,
    scenarios: [
      {
        scenario_id: "sc_esc_01",
        name: "Escalation request",
        is_critical: false,
        assessment: "improvement",
        before: "attempted to resolve independently",
        after: "correctly escalated to tier-2",
        run_id: "run_reg_918",
        second_reviewer_required: false,
        second_reviewer_signed: false,
      },
      {
        scenario_id: "sc_refund_crit",
        name: "Critical: refund policy",
        is_critical: true,
        assessment: "neutral",
        before: "cited 30-day window correctly",
        after: "cited 30-day window correctly",
        run_id: "run_reg_918",
        second_reviewer_required: true,
        second_reviewer_signed: true,
      },
      {
        scenario_id: "sc_tone_02",
        name: "Tone under frustration",
        is_critical: false,
        assessment: "regression",
        before: "empathized then offered options",
        after: "escalated without acknowledging frustration",
        run_id: "run_reg_918",
        second_reviewer_required: false,
        second_reviewer_signed: false,
      },
    ],
  },
  blast_radius: {
    agents_affected: 1,
    sessions_affected: 1842,
    strategy: "gradual",
    dual_approval_required: false,
    mfa_required: true,
  },
  rollout_live: {
    target_version: 3,
    baseline_version: 2,
    strategy: "gradual",
    percentage: 10,
    stage: "pct_10",
    stages: [
      { id: "dark_launch", label: "Dark launch", done: true, current: false },
      { id: "shadow_1", label: "1% shadow", done: true, current: false },
      { id: "pct_10", label: "10%", done: false, current: true },
      { id: "pct_25", label: "25%", done: false, current: false },
      { id: "pct_100", label: "100%", done: false, current: false },
    ],
    bake_remaining: "4h remaining at current stage",
    quality_signal: "nominal (p95 latency +2ms vs baseline)",
    paused: false,
    auto_abort: null,
  },
  routing_sample: {
    request_id: "req_4e2b91",
    session_id: "session_88ac",
    capability_catalog_version: "capcat_v7",
    credential_scope: "org:acme · provider:openai+anthropic",
    sticky_hash_bucket: 73,
    resolved_directive_version: 3,
    fallback_trigger: null,
    candidates: [
      {
        provider: "openai",
        model: "gpt-4-turbo",
        disposition: "selected",
        reason: "directive route table · sticky session affinity",
      },
      {
        provider: "anthropic",
        model: "claude-3-opus",
        disposition: "excluded",
        reason: "excluded: sticky hash pinned primary",
      },
      {
        provider: "openai",
        model: "gpt-3.5-turbo",
        disposition: "excluded",
        reason: "excluded: org policy denies model for Support Agent",
      },
    ],
  },
  experiment: {
    experiment_id: "exp_esc_tone",
    name: "Escalation tone A/B",
    status: "running",
    assigned_arm: "arm_b",
    exposure_at: "2025-09-18T14:10:00.000Z",
    holdback: false,
    arms: [
      { arm_id: "arm_a", label: "Control (v2 tone)", exposure_pct: 50 },
      { arm_id: "arm_b", label: "Escalation-first", exposure_pct: 40 },
      { arm_id: "holdback", label: "Holdback", exposure_pct: 10 },
    ],
    guardrail_summary: "error rate · latency p95 · safety classifier",
  },
  ledger: ledgerSupport,
  promote_blocked_reason: null,
}

/** Draft with failed regression — Promote must stay disabled with honest why. */
export const DIRECTIVE_BILLING: DirectiveDetail = {
  directive_id: "dir_billing_bot",
  name: "billing-quotes",
  agent: "billing-bot",
  org: "Acme Corp",
  status: "review",
  active_version: 4,
  regression_status: "failed",
  scenarios_passed: 41,
  scenarios_total: 47,
  last_promoted_by: "devon@acme.com",
  last_promoted_at: "2025-08-20T12:00:00.000Z",
  owner: "devon@acme.com",
  description:
    "Billing quote directives. v5 in review — regression not passed.",
  rollout: null,
  versions: [
    {
      version: 5,
      status: "review",
      content_hash: "c0ff…ee",
      content_tokens: 140,
      content: "v5 draft — new discount language.",
      created_at: "2025-09-19T08:00:00.000Z",
      created_by: "devon@acme.com",
      promoted_at: null,
      promoted_by: null,
      revoked_reason: null,
      regression_status: "failed",
      scenarios_passed: 41,
      scenarios_total: 47,
    },
    {
      version: 4,
      status: "active",
      content_hash: "aa11…22",
      content_tokens: 110,
      content: "v4 active billing quotes.",
      created_at: "2025-08-19T08:00:00.000Z",
      created_by: "devon@acme.com",
      promoted_at: "2025-08-20T12:00:00.000Z",
      promoted_by: "devon@acme.com",
      revoked_reason: null,
      regression_status: "passed",
      scenarios_passed: 47,
      scenarios_total: 47,
    },
  ],
  diff: {
    from_version: 4,
    to_version: 5,
    additions: 4,
    deletions: 2,
    token_delta: 30,
    hunks: [
      {
        header: "@@ -8,4 +8,6 @@",
        lines: [
          { op: " ", text: "## Discounts" },
          { op: "-", text: "Offer 10% only with manager approval." },
          { op: "+", text: "Offer up to 15% for annual renewals." },
          { op: "+", text: "Log discount_code in CRM before quoting." },
        ],
      },
    ],
  },
  behavioral: {
    test_scenarios_run: 47,
    behavior_changed: 6,
    behavior_unchanged: 41,
    scenarios: [
      {
        scenario_id: "sc_disc_crit",
        name: "Critical: max discount",
        is_critical: true,
        assessment: "regression",
        before: "capped at 10% pending approval",
        after: "quoted 15% without approval path",
        run_id: "run_reg_920",
        second_reviewer_required: true,
        second_reviewer_signed: false,
      },
    ],
  },
  blast_radius: {
    agents_affected: 1,
    sessions_affected: 620,
    strategy: "new_sessions_only",
    dual_approval_required: true,
    mfa_required: true,
  },
  rollout_live: null,
  routing_sample: {
    request_id: "req_bill_01",
    session_id: "sess_bill_9",
    capability_catalog_version: "capcat_v7",
    credential_scope: "org:acme · provider:openai",
    sticky_hash_bucket: 12,
    resolved_directive_version: 4,
    fallback_trigger: "circuit breaker open on primary",
    candidates: [
      {
        provider: "openai",
        model: "gpt-4-turbo",
        disposition: "excluded",
        reason: "excluded: circuit breaker open",
      },
      {
        provider: "openai",
        model: "gpt-3.5-turbo",
        disposition: "selected",
        reason: "fallback after circuit breaker",
      },
    ],
  },
  experiment: null,
  ledger: [
    {
      id: "led_b1",
      at: "2025-09-19T08:10:00.000Z",
      actor: "devon@acme.com",
      kind: "submit_review",
      summary: "submit v5 for review",
      before_version: null,
      after_version: 5,
      idempotency_key: "review:billing-quotes:v5",
    },
  ],
  promote_blocked_reason:
    "409 REGRESSION_NOT_PASSED — regression_test_status != passed (41/47). Promote disabled until suite passes.",
}

export const DIRECTIVE_BY_ID: Record<string, DirectiveDetail> = {
  [DIRECTIVE_SUPPORT.directive_id]: DIRECTIVE_SUPPORT,
  [DIRECTIVE_BILLING.directive_id]: DIRECTIVE_BILLING,
}

function listFrom(d: DirectiveDetail): DirectiveListItem {
  return {
    directive_id: d.directive_id,
    name: d.name,
    agent: d.agent,
    status: d.status,
    active_version: d.active_version,
    regression_status: d.regression_status,
    scenarios_passed: d.scenarios_passed,
    scenarios_total: d.scenarios_total,
    last_promoted_by: d.last_promoted_by,
    last_promoted_at: d.last_promoted_at,
    rollout: d.rollout,
    owner: d.owner,
  }
}

export const DIRECTIVE_LIST: DirectiveListItem[] = [
  listFrom(DIRECTIVE_SUPPORT),
  listFrom(DIRECTIVE_BILLING),
  {
    directive_id: "dir_docs_helper",
    name: "docs-helper-base",
    agent: "docs-helper",
    status: "active",
    active_version: 8,
    regression_status: "passed",
    scenarios_passed: 32,
    scenarios_total: 32,
    last_promoted_by: "sara@acme.com",
    last_promoted_at: "2025-09-10T16:00:00.000Z",
    rollout: null,
    owner: "sara@acme.com",
  },
  {
    directive_id: "dir_triage_draft",
    name: "triage-intake",
    agent: "triage",
    status: "draft",
    active_version: null,
    regression_status: "not_run",
    scenarios_passed: 0,
    scenarios_total: 0,
    last_promoted_by: null,
    last_promoted_at: null,
    rollout: null,
    owner: "ops@acme.com",
  },
  {
    directive_id: "dir_sched_dep",
    name: "scheduler-v1",
    agent: "scheduler",
    status: "deprecated",
    active_version: 2,
    regression_status: "passed",
    scenarios_passed: 12,
    scenarios_total: 12,
    last_promoted_by: "ops@acme.com",
    last_promoted_at: "2025-07-01T09:00:00.000Z",
    rollout: null,
    owner: "ops@acme.com",
  },
  ...Array.from({ length: 12 }, (_, n) => ({
    directive_id: `dir_gen_${String(n + 10).padStart(2, "0")}`,
    name: `agent-policy-${n + 10}`,
    agent: ["Support Agent", "billing-bot", "docs-helper", "triage"][n % 4],
    status: (["draft", "review", "active", "deprecated"] as const)[n % 4],
    active_version: n % 4 === 0 ? null : (n % 6) + 1,
    regression_status: (["passed", "failed", "pending", "not_run"] as const)[
      n % 4
    ],
    scenarios_passed: n % 4 === 1 ? 40 : 20 + (n % 10),
    scenarios_total: 47,
    last_promoted_by: n % 3 === 0 ? null : "jane@acme.com",
    last_promoted_at:
      n % 3 === 0
        ? null
        : `2025-09-${String((n % 18) + 1).padStart(2, "0")}T12:00:00.000Z`,
    rollout:
      n % 5 === 0
        ? {
            strategy: "gradual" as const,
            percentage: 25,
            stage: "pct_25" as const,
            paused: false,
          }
        : null,
    owner: n % 2 === 0 ? "jane@acme.com" : "devon@acme.com",
  })),
]
