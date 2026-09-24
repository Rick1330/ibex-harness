"use client"

import {
  effectiveAgentQuota,
  effectiveMemoryQuota,
  effectiveTokenQuota,
  overrideFields,
  TIER_LIMITS,
  type OrgQuotaSnapshot,
  type OrgTier,
} from "@/lib/org/tier"
import { cn } from "@/lib/utils"

const compact = new Intl.NumberFormat("en-US", {
  notation: "compact",
  maximumFractionDigits: 1,
})

const FEATURE_KEYS = [
  "drift_detection_enabled",
  "behavioral_fingerprinting",
  "directive_versioning",
  "marketplace_access",
  "federation_enabled",
  "sso_enabled",
] as const

/** Shared between Billing A1 and Settings B1 — one rendering of organizations + tier_limits. */
export function TierQuotaCard({
  org,
  className,
  showComparison = true,
}: {
  org: OrgQuotaSnapshot
  className?: string
  showComparison?: boolean
}) {
  const overrides = overrideFields(org)
  const tokenQ = effectiveTokenQuota(org)
  const memQ = effectiveMemoryQuota(org)
  const agentQ = effectiveAgentQuota(org)
  const daysLeft = Math.max(
    0,
    Math.ceil(
      (new Date(org.resets_at).getTime() - Date.UTC(2026, 1, 11, 16)) /
        86_400_000,
    ),
  )

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
            Plan & usage
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[18px] font-medium">
              {org.tier}
            </span>
            <StatusPill status={org.status} />
            {overrides.length > 0 ? (
              <span
                className="rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-400"
                title={`Overrides: ${overrides.join(", ")}`}
              >
                Custom override active
              </span>
            ) : null}
          </div>
          <div className="mt-1 text-[12px] text-muted-foreground">
            cycle anchor{" "}
            <span className="font-mono text-foreground">
              {org.billing_cycle_anchor.slice(0, 10)}
            </span>
            {org.stripe_customer_id_masked ? (
              <>
                {" "}
                · stripe{" "}
                <span className="font-mono text-foreground">
                  {org.stripe_customer_id_masked}
                </span>
              </>
            ) : (
              <span> · no stripe customer</span>
            )}
          </div>
        </div>
        <div className="text-right text-[12px] text-muted-foreground">
          resets in{" "}
          <span className="font-mono text-foreground">{daysLeft}d</span>
          <div className="font-mono text-[11px]">
            {org.resets_at.slice(0, 10)}
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <QuotaBar
          label="tokens"
          used={org.tokens_used}
          quota={tokenQ}
          override={org.custom_token_quota_monthly != null}
          tierDefault={org.tier_limits.monthly_tokens}
        />
        <QuotaBar
          label="memories"
          used={org.memory_count}
          quota={memQ}
          override={org.custom_memory_quota != null}
          tierDefault={org.tier_limits.max_memories}
        />
        <QuotaBar
          label="agents"
          used={org.agent_count}
          quota={agentQ}
          override={org.custom_agent_quota != null}
          tierDefault={org.tier_limits.max_agents}
        />
      </div>

      {showComparison ? <TierLimitsGrid current={org.tier} /> : null}
    </div>
  )
}

function StatusPill({ status }: { status: OrgQuotaSnapshot["status"] }) {
  const tone =
    status === "active"
      ? "border-foreground/30 bg-muted text-foreground"
      : status === "trial"
        ? "border-sky-500/40 bg-sky-500/10 text-sky-800 dark:text-sky-300"
        : "border-destructive/40 bg-destructive/10 text-destructive"
  return (
    <span
      className={cn(
        "rounded-md border px-1.5 py-0.5 font-mono text-[11px]",
        tone,
      )}
    >
      {status}
    </span>
  )
}

function QuotaBar({
  label,
  used,
  quota,
  override,
  tierDefault,
}: {
  label: string
  used: number
  quota: number
  override: boolean
  tierDefault: number
}) {
  const pct = quota > 0 ? Math.min(100, (used / quota) * 100) : 0
  return (
    <div className="rounded-md border border-border/70 px-3 py-2.5">
      <div className="flex items-center justify-between text-[11px] text-muted-foreground">
        <span className="uppercase tracking-wide">{label}</span>
        {override ? (
          <span
            className="text-amber-700 dark:text-amber-400"
            title={`Tier default ${compact.format(tierDefault)} · override ${compact.format(quota)}`}
          >
            override
          </span>
        ) : null}
      </div>
      <div className="mt-1 font-mono text-[14px] tabular-nums">
        {compact.format(used)}
        <span className="text-muted-foreground">
          {" "}
          / {compact.format(quota)}
        </span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-sm bg-muted">
        <div
          className="h-full rounded-sm bg-foreground"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function TierLimitsGrid({ current }: { current: OrgTier }) {
  const tiers: OrgTier[] = ["free", "pro", "enterprise"]
  const rows: Array<{
    label: string
    value: (t: OrgTier) => string
  }> = [
    {
      label: "monthly tokens",
      value: (t) => compact.format(TIER_LIMITS[t].monthly_tokens),
    },
    {
      label: "max memories",
      value: (t) => compact.format(TIER_LIMITS[t].max_memories),
    },
    {
      label: "max agents",
      value: (t) => String(TIER_LIMITS[t].max_agents),
    },
    {
      label: "sessions/day",
      value: (t) => compact.format(TIER_LIMITS[t].max_sessions_per_day),
    },
    {
      label: "audit retention",
      value: (t) => `${TIER_LIMITS[t].audit_log_retention_days}d`,
    },
    {
      label: "RPM / RPD",
      value: (t) =>
        `${TIER_LIMITS[t].rpm} / ${compact.format(TIER_LIMITS[t].rpd)}`,
    },
    {
      label: "support",
      value: (t) => TIER_LIMITS[t].support_level,
    },
    ...FEATURE_KEYS.map((k) => ({
      label: k.replace(/_enabled$/, "").replace(/_/g, " "),
      value: (t: OrgTier) => (TIER_LIMITS[t][k] ? "on" : "off"),
    })),
  ]

  return (
    <div className="overflow-x-auto rounded-md border border-border/70">
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr className="border-b border-border/80">
            <th className="px-3 py-2 text-left text-[11px] font-medium text-muted-foreground">
              tier_limits
            </th>
            {tiers.map((t) => (
              <th
                key={t}
                className={cn(
                  "px-3 py-2 text-left font-mono text-[11px]",
                  t === current
                    ? "bg-muted/60 font-medium text-foreground"
                    : "text-muted-foreground",
                )}
              >
                {t}
                {t === current ? " · current" : ""}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.label} className="border-b border-border/50">
              <td className="px-3 py-1.5 text-muted-foreground">{r.label}</td>
              {tiers.map((t) => (
                <td
                  key={t}
                  className={cn(
                    "px-3 py-1.5 font-mono tabular-nums",
                    t === current && "bg-muted/40 text-foreground",
                  )}
                >
                  {r.value(t)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
