/**
 * Shared org tier / quota contract — used by Billing A1 and Settings B1.
 * Sourced from organizations row + ibex_billing.tier_limits.
 */

export type OrgTier = "free" | "pro" | "enterprise" | "self_hosted"

export type OrgBillingStatus = "active" | "suspended" | "cancelled" | "trial"

export type TierLimits = {
  tier: OrgTier
  monthly_tokens: number
  max_memories: number
  max_agents: number
  max_sessions_per_day: number
  audit_log_retention_days: number
  rpm: number
  rpd: number
  support_level: string
  drift_detection_enabled: boolean
  behavioral_fingerprinting: boolean
  directive_versioning: boolean
  marketplace_access: boolean
  federation_enabled: boolean
  sso_enabled: boolean
}

export type OrgQuotaSnapshot = {
  org_id: string
  name: string
  slug: string
  tier: OrgTier
  status: OrgBillingStatus
  billing_cycle_anchor: string
  /** Masked — never full Stripe id. */
  stripe_customer_id_masked: string | null
  tier_limits: TierLimits
  /** Org-level overrides — null means use tier default. */
  custom_token_quota_monthly: number | null
  custom_memory_quota: number | null
  custom_agent_quota: number | null
  tokens_used: number
  memory_count: number
  agent_count: number
  resets_at: string
}

export const TIER_LIMITS: Record<OrgTier, TierLimits> = {
  free: {
    tier: "free",
    monthly_tokens: 1_000_000,
    max_memories: 1_000,
    max_agents: 3,
    max_sessions_per_day: 100,
    audit_log_retention_days: 7,
    rpm: 30,
    rpd: 5_000,
    support_level: "community",
    drift_detection_enabled: false,
    behavioral_fingerprinting: false,
    directive_versioning: false,
    marketplace_access: false,
    federation_enabled: false,
    sso_enabled: false,
  },
  pro: {
    tier: "pro",
    monthly_tokens: 50_000_000,
    max_memories: 100_000,
    max_agents: 25,
    max_sessions_per_day: 5_000,
    audit_log_retention_days: 90,
    rpm: 300,
    rpd: 100_000,
    support_level: "email",
    drift_detection_enabled: true,
    behavioral_fingerprinting: true,
    directive_versioning: true,
    marketplace_access: true,
    federation_enabled: false,
    sso_enabled: false,
  },
  enterprise: {
    tier: "enterprise",
    monthly_tokens: 500_000_000,
    max_memories: 2_000_000,
    max_agents: 500,
    max_sessions_per_day: 100_000,
    audit_log_retention_days: 365,
    rpm: 2_000,
    rpd: 2_000_000,
    support_level: "dedicated",
    drift_detection_enabled: true,
    behavioral_fingerprinting: true,
    directive_versioning: true,
    marketplace_access: true,
    federation_enabled: true,
    sso_enabled: true,
  },
  self_hosted: {
    tier: "self_hosted",
    monthly_tokens: 0,
    max_memories: 0,
    max_agents: 0,
    max_sessions_per_day: 0,
    audit_log_retention_days: 365,
    rpm: 0,
    rpd: 0,
    support_level: "self",
    drift_detection_enabled: true,
    behavioral_fingerprinting: true,
    directive_versioning: true,
    marketplace_access: true,
    federation_enabled: true,
    sso_enabled: true,
  },
}

export const ORG_QUOTA: OrgQuotaSnapshot = {
  org_id: "org_acme",
  name: "Acme Corp",
  slug: "acme",
  tier: "pro",
  status: "active",
  billing_cycle_anchor: "2026-02-01T00:00:00.000Z",
  stripe_customer_id_masked: "cus_••••3f2a",
  tier_limits: TIER_LIMITS.pro,
  custom_token_quota_monthly: null,
  custom_memory_quota: null,
  custom_agent_quota: 40,
  tokens_used: 28_400_000,
  memory_count: 12_908,
  agent_count: 12,
  resets_at: "2026-03-01T00:00:00.000Z",
}

export function effectiveTokenQuota(o: OrgQuotaSnapshot) {
  return o.custom_token_quota_monthly ?? o.tier_limits.monthly_tokens
}

export function effectiveMemoryQuota(o: OrgQuotaSnapshot) {
  return o.custom_memory_quota ?? o.tier_limits.max_memories
}

export function effectiveAgentQuota(o: OrgQuotaSnapshot) {
  return o.custom_agent_quota ?? o.tier_limits.max_agents
}

export function overrideFields(o: OrgQuotaSnapshot): string[] {
  const out: string[] = []
  if (o.custom_token_quota_monthly != null)
    out.push("custom_token_quota_monthly")
  if (o.custom_memory_quota != null) out.push("custom_memory_quota")
  if (o.custom_agent_quota != null) out.push("custom_agent_quota")
  return out
}
