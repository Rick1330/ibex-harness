import { ORG_QUOTA } from "@/lib/org/tier"
import type {
  BillingPageV2,
  BudgetPeriod,
  RateCard,
  UsageQueryResult,
  UsageQueryShape,
} from "./types"

const pricesV12 = [
  {
    provider: "openai",
    model_pattern: "gpt-4-turbo*",
    input_cents_per_1k: 1.0,
    output_cents_per_1k: 3.0,
  },
  {
    provider: "openai",
    model_pattern: "gpt-4*",
    input_cents_per_1k: 3.0,
    output_cents_per_1k: 6.0,
  },
  {
    provider: "openai",
    model_pattern: "gpt-3.5*",
    input_cents_per_1k: 0.05,
    output_cents_per_1k: 0.15,
  },
  {
    provider: "anthropic",
    model_pattern: "claude-*",
    input_cents_per_1k: 0.8,
    output_cents_per_1k: 2.4,
  },
  {
    provider: "anthropic",
    model_pattern: "claude-3-opus*",
    input_cents_per_1k: 1.5,
    output_cents_per_1k: 7.5,
  },
]

const pricesV13Draft = [
  ...pricesV12.map((p) =>
    p.model_pattern === "gpt-4-turbo*"
      ? { ...p, input_cents_per_1k: 0.9, output_cents_per_1k: 2.7 }
      : p,
  ),
  {
    provider: "google",
    model_pattern: "gemini-*",
    input_cents_per_1k: 0.35,
    output_cents_per_1k: 1.05,
  },
]

export const RATE_CARDS: RateCard[] = [
  {
    card_id: "rc_default",
    name: "Default production",
    currency: "USD",
    status: "published",
    versions: [
      {
        version_id: "rcv_12",
        version: 12,
        created_at: "2026-01-15T00:00:00.000Z",
        created_by: "devon@acme.com",
        prices: pricesV12,
      },
      {
        version_id: "rcv_11",
        version: 11,
        created_at: "2025-11-01T00:00:00.000Z",
        created_by: "sara@acme.com",
        prices: pricesV12.map((p) => ({
          ...p,
          input_cents_per_1k: +(p.input_cents_per_1k * 1.2).toFixed(2),
          output_cents_per_1k: +(p.output_cents_per_1k * 1.2).toFixed(2),
        })),
      },
    ],
  },
  {
    card_id: "rc_draft",
    name: "Q1 revision",
    currency: "USD",
    status: "draft",
    versions: [
      {
        version_id: "rcv_13d",
        version: 13,
        created_at: "2026-02-10T09:00:00.000Z",
        created_by: "devon@acme.com",
        prices: pricesV13Draft,
      },
    ],
  },
  {
    card_id: "rc_legacy",
    name: "2024 legacy",
    currency: "USD",
    status: "archived",
    versions: [
      {
        version_id: "rcv_04",
        version: 4,
        created_at: "2024-06-01T00:00:00.000Z",
        created_by: "sara@acme.com",
        prices: [
          {
            provider: "openai",
            model_pattern: "gpt-4*",
            input_cents_per_1k: 4,
            output_cents_per_1k: 8,
          },
        ],
      },
    ],
  },
]

function burnSeries(
  cap: number,
  spent: number,
): BudgetPeriod["daily_spend_cents"] {
  const days = 11
  return Array.from({ length: days }, (_, i) => ({
    day: `2026-02-${String(i + 1).padStart(2, "0")}`,
    cumulative_cents: Math.round((spent / (days - 1)) * i),
  })).map((d, i, arr) =>
    i === arr.length - 1 ? { ...d, cumulative_cents: spent } : d,
  )
}

export const BUDGETS: BudgetPeriod[] = [
  {
    period_id: "bp_2026_02",
    period_start: "2026-02-01T00:00:00.000Z",
    period_end: "2026-02-28T23:59:59.000Z",
    cap_cents: 150_000,
    spent_cents_cached: 128_455,
    enforcement_mode: "hard_cap",
    daily_spend_cents: burnSeries(150_000, 128_455),
  },
  {
    period_id: "bp_2026_01",
    period_start: "2026-01-01T00:00:00.000Z",
    period_end: "2026-01-31T23:59:59.000Z",
    cap_cents: 150_000,
    spent_cents_cached: 141_200,
    enforcement_mode: "alert_only",
    daily_spend_cents: burnSeries(150_000, 141_200),
  },
]

function usageShape(
  shape: UsageQueryShape,
  partial: boolean,
  truncated: boolean,
  matched: number,
  rows: UsageQueryResult["rows"],
): UsageQueryResult {
  return {
    shape,
    completeness: partial ? "partial" : "complete",
    truncated,
    matched_count: matched,
    returned_count: rows.length,
    rows,
  }
}

export const USAGE_BY_SHAPE: Record<UsageQueryShape, UsageQueryResult> = {
  org_time_aggregate: usageShape("org_time_aggregate", true, false, 264, [
    {
      key: "2026-02-11T14",
      label: "2026-02-11 14:00Z",
      value: 8420,
      estimated_cost_cents: 6120,
      completeness: "partial",
    },
    {
      key: "2026-02-11T13",
      label: "2026-02-11 13:00Z",
      value: 7010,
      estimated_cost_cents: 4980,
      completeness: "complete",
    },
    {
      key: "2026-02-11T12",
      label: "2026-02-11 12:00Z",
      value: 6280,
      estimated_cost_cents: 4410,
      completeness: "complete",
    },
  ]),
  agent_session_breakdown: usageShape(
    "agent_session_breakdown",
    false,
    true,
    1842,
    [
      {
        key: "agt_01h9support",
        label: "support-agent · 312 sessions",
        value: 920_400,
        estimated_cost_cents: 71_020,
        completeness: "complete",
      },
      {
        key: "agt_billing",
        label: "billing-bot · 98 sessions",
        value: 410_200,
        estimated_cost_cents: 31_240,
        completeness: "complete",
      },
    ],
  ),
  request_point_lookup: usageShape("request_point_lookup", false, false, 1, [
    {
      key: "req_88ac01",
      label: "gpt-4-turbo · matched gpt-4-turbo*",
      value: 1,
      estimated_cost_cents: 42,
      completeness: "complete",
      request_id: "req_88ac01",
    },
  ]),
  fallback_attribution: usageShape("fallback_attribution", false, false, 48, [
    {
      key: "openai→anthropic",
      label: "fallback openai → anthropic",
      value: 48,
      estimated_cost_cents: 890,
      completeness: "complete",
    },
  ]),
  tool_correlation: usageShape("tool_correlation", true, true, 12_400, [
    {
      key: "kb.search",
      label: "kb.search",
      value: 4100,
      estimated_cost_cents: 2200,
      completeness: "partial",
    },
    {
      key: "crm.get",
      label: "crm.get",
      value: 2800,
      estimated_cost_cents: 1600,
      completeness: "partial",
    },
  ]),
}

export const BILLING_V2: BillingPageV2 = {
  org: ORG_QUOTA,
  rate_cards: RATE_CARDS,
  budgets: BUDGETS,
  enforcement: [
    {
      decision_id: "ed_91a",
      decided_at: "2026-02-11T14:02:11.000Z",
      decision: "allow",
      reason: "within_cap",
      remaining_cents: 42_180,
      request_id: "req_4e2b91",
      trace_id: "trace_a91f7c",
      agent_slug: "support-agent",
    },
    {
      decision_id: "ed_90b",
      decided_at: "2026-02-11T09:18:44.000Z",
      decision: "deny",
      reason: "BUDGET_EXCEEDED",
      remaining_cents: 0,
      request_id: "req_88ac01",
      trace_id: "trace_b02e44",
      agent_slug: "billing-bot",
    },
    {
      decision_id: "ed_89c",
      decided_at: "2026-02-10T22:01:02.000Z",
      decision: "unavailable",
      reason: "ErrBudgetUnavailable",
      remaining_cents: null,
      request_id: "req_c77e01",
      trace_id: null,
      agent_slug: "docs-helper",
    },
    {
      decision_id: "ed_88d",
      decided_at: "2026-02-10T16:40:00.000Z",
      decision: "allow",
      reason: "alert_only_overage",
      remaining_cents: -4_200,
      request_id: "req_d12ab9",
      trace_id: "trace_c77e01",
      agent_slug: "support-agent",
    },
  ],
  usage_by_shape: USAGE_BY_SHAPE,
  dry_run_preview: [
    {
      request_id: "req_4e2b91",
      model: "gpt-4-turbo",
      matched_pattern_old: "gpt-4-turbo*",
      matched_pattern_new: "gpt-4-turbo*",
      estimated_cents_old: 38,
      estimated_cents_new: 34,
    },
    {
      request_id: "req_88ac01",
      model: "claude-3-opus",
      matched_pattern_old: "claude-*",
      matched_pattern_new: "claude-3-opus*",
      estimated_cents_old: 120,
      estimated_cents_new: 180,
    },
  ],
  reconciliation: {
    status: "deferred",
    reason: "no_invoice_source",
    issue: "#859",
  },
}

/** Left-to-right first-match — mirrors packages/billing/estimate.go. */
export function matchModelPattern(
  model: string,
  prices: { model_pattern: string }[],
): string | null {
  for (const p of prices) {
    const re = new RegExp(
      "^" +
        p.model_pattern
          .replace(/[.+^${}()|[\]\\]/g, "\\$&")
          .replace(/\*/g, ".*") +
        "$",
    )
    if (re.test(model)) return p.model_pattern
  }
  return null
}

export function centsUsd(cents: number) {
  return cents / 100
}

export function projectExhaustion(
  spent: number,
  cap: number,
  daily: BudgetPeriod["daily_spend_cents"],
): string | null {
  if (daily.length < 2 || spent >= cap) return spent >= cap ? "exhausted" : null
  const first = daily[0]!.cumulative_cents
  const last = daily[daily.length - 1]!.cumulative_cents
  const days = daily.length - 1
  const rate = (last - first) / days
  if (rate <= 0) return null
  const remain = cap - spent
  const daysLeft = Math.ceil(remain / rate)
  const d = new Date(Date.UTC(2026, 1, 11))
  d.setUTCDate(d.getUTCDate() + daysLeft)
  return d.toISOString().slice(0, 10)
}
