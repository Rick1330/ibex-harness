/**
 * Billing v2 — ibex_billing rate_cards / budget_periods / enforcement_decisions
 * + UsageQueryRequest.shape enum. estimated only until #859.
 */

import type { OrgQuotaSnapshot } from "@/lib/org/tier"

export type RateCardStatus = "draft" | "published" | "archived"
export type EnforcementMode = "alert_only" | "hard_cap"
export type EnforcementDecisionKind = "allow" | "deny" | "unavailable"

export type UsageQueryShape =
  | "org_time_aggregate"
  | "agent_session_breakdown"
  | "request_point_lookup"
  | "fallback_attribution"
  | "tool_correlation"

export type RatePriceRow = {
  provider: string
  model_pattern: string
  input_cents_per_1k: number
  output_cents_per_1k: number
}

export type RateCardVersion = {
  version_id: string
  version: number
  created_at: string
  created_by: string
  prices: RatePriceRow[]
}

export type RateCard = {
  card_id: string
  name: string
  currency: string
  status: RateCardStatus
  versions: RateCardVersion[]
}

export type DryRunDiffRow = {
  request_id: string
  model: string
  matched_pattern_old: string
  matched_pattern_new: string
  estimated_cents_old: number
  estimated_cents_new: number
}

export type BudgetPeriod = {
  period_id: string
  period_start: string
  period_end: string
  cap_cents: number
  /** Cached rollup — not real-time. */
  spent_cents_cached: number
  enforcement_mode: EnforcementMode
  daily_spend_cents: Array<{ day: string; cumulative_cents: number }>
}

export type EnforcementDecision = {
  decision_id: string
  decided_at: string
  decision: EnforcementDecisionKind
  reason: string
  remaining_cents: number | null
  request_id: string
  trace_id: string | null
  agent_slug: string | null
}

export type UsageRow = {
  key: string
  label: string
  value: number
  estimated_cost_cents: number
  completeness: "complete" | "partial"
  request_id?: string
}

export type UsageQueryResult = {
  shape: UsageQueryShape
  completeness: "complete" | "partial"
  truncated: boolean
  matched_count: number
  returned_count: number
  rows: UsageRow[]
}

export type ReconciliationStatus = {
  status: "deferred"
  reason: "no_invoice_source"
  issue: "#859"
}

export type BillingPageV2 = {
  org: OrgQuotaSnapshot
  rate_cards: RateCard[]
  budgets: BudgetPeriod[]
  enforcement: EnforcementDecision[]
  usage_by_shape: Record<UsageQueryShape, UsageQueryResult>
  dry_run_preview: DryRunDiffRow[]
  reconciliation: ReconciliationStatus
}
