import {
  AGENT_NOW,
  AGENT_TABS,
  agentBudgetLeftPct,
  agentBudgetLeftUsd,
  agentBudgetUsedPct,
  agentCountLabel,
  agentHealthLabel,
  agentPctLabel,
  type AgentBudget,
  type AgentDetail,
  type AgentTab,
} from "./agent-preview"

/** Every number on both pages is scoped to the preview contract window. */
export const AGENT_PERIOD_LABEL = "last 14 days"
export const AGENT_PERIOD_TITLE = "Last 14 days"

/** Money: 3 significant digits in tables and tiles; cents only below $10. */
export function formatAgentMoney(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  if (value === 0) return "$0"
  if (value < 10) return `$${value.toFixed(2)}`
  if (value < 1_000) return `$${Math.round(value).toLocaleString("en-US")}`
  const thousands = Number((value / 1_000).toPrecision(3))
  return `$${thousands.toLocaleString("en-US", { maximumFractionDigits: 2 })}k`
}

/** Counts: 3 significant digits above 1,000 (`12.1k`, `2.84k`, `980`). */
export function formatAgentCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  if (value < 1_000) return value.toLocaleString("en-US")
  const thousands = Number((value / 1_000).toPrecision(3))
  return `${thousands.toLocaleString("en-US", { maximumFractionDigits: 2 })}k`
}

export function formatAgentPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—"
  return `${value.toFixed(digits)}%`
}

export function formatAgentDuration(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—"
  if (value < 1_000) return `${Math.round(value)} ms`
  return `${(value / 1_000).toFixed(value >= 10_000 ? 1 : 2)} s`
}

export function formatAgentRelative(iso: string | null | undefined, now = AGENT_NOW): string {
  if (!iso) return "Never"
  const time = Date.parse(iso)
  if (Number.isNaN(time)) return "Never"
  const delta = Math.max(0, now - time)
  if (delta < 45_000) return "just now"
  if (delta < 3_600_000) return `${Math.max(1, Math.round(delta / 60_000))}m ago`
  if (delta < 86_400_000) return `${Math.round(delta / 3_600_000)}h ago`
  return `${Math.round(delta / 86_400_000)}d ago`
}

export function formatAgentDay(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(date)
}

export function formatAgentDate(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date)
}

export function formatAgentStamp(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).formatToParts(date)
  const part = (type: Intl.DateTimeFormatPartTypes): string => parts.find((entry) => entry.type === type)?.value ?? ""
  return `${part("day")} ${part("month")} ${part("year")}, ${part("hour")}:${part("minute")} UTC`
}

export function formatAgentClock(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(date)
}

export function formatAgentDayHeading(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return new Intl.DateTimeFormat("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date)
}

export function agentDayKey(iso: string): string {
  return iso.slice(0, 10)
}

export type AgentBudgetSegments = {
  usedPct: number
  committedPct: number
  leftPct: number
  totalUsd: number
  usedUsd: number
  committedUsd: number
  leftUsd: number
  floorPct: number
  state: "healthy" | "low" | "exhausted"
}

export function agentBudgetSegments(budget: AgentBudget): AgentBudgetSegments {
  const leftPct = agentBudgetLeftPct(budget)
  return {
    usedPct: agentBudgetUsedPct(budget),
    committedPct: budget.totalUsd > 0 ? (budget.committedUsd / budget.totalUsd) * 100 : 0,
    leftPct,
    totalUsd: budget.totalUsd,
    usedUsd: budget.usedUsd,
    committedUsd: budget.committedUsd,
    leftUsd: agentBudgetLeftUsd(budget),
    floorPct: budget.floorPct,
    state: leftPct <= 0 ? "exhausted" : leftPct < budget.floorPct ? "low" : "healthy",
  }
}

export function agentBudgetSummary(budget: AgentBudget): string {
  return `${formatAgentMoney(budget.usedUsd)} of ${formatAgentMoney(budget.totalUsd)} used · ${formatAgentMoney(agentBudgetLeftUsd(budget))} left`
}

export type AgentTabBadge = {
  tab: AgentTab
  label: string
  tone: "neutral" | "warning" | "destructive"
  srLabel?: string
}

export function agentTabBadges(agent: AgentDetail): AgentTabBadge[] {
  const badges: AgentTabBadge[] = []
  badges.push({ tab: "runs", label: formatAgentCount(agent.stats.runs), tone: "neutral" })
  badges.push({
    tab: "sessions",
    label:
      agent.stats.activeSessions > 0
        ? `${formatAgentCount(agent.stats.sessions)} · ${agent.stats.activeSessions} live`
        : formatAgentCount(agent.stats.sessions),
    tone: "neutral",
  })
  badges.push({
    tab: "directives",
    label: agent.directive ? `v${agent.directive.version}` : "None",
    tone: "neutral",
  })
  const auditRules = agent.policy?.rules.filter((rule) => rule.mode === "audit").length ?? 0
  badges.push({
    tab: "policies",
    label: agent.policy ? (auditRules > 0 ? `⚠ ${auditRules}` : "✓") : "None",
    tone: auditRules > 0 ? "warning" : "neutral",
    srLabel: agent.policy ? (auditRules > 0 ? `${auditRules} rules in audit mode` : "Policy enforced") : "No policy",
  })
  badges.push({
    tab: "memories",
    label:
      agent.stats.quarantined > 0
        ? `${formatAgentCount(agent.stats.memories)} · ⚠${agent.stats.quarantined}`
        : formatAgentCount(agent.stats.memories),
    tone: agent.stats.quarantined > 0 ? "warning" : "neutral",
    srLabel:
      agent.stats.quarantined > 0
        ? `${agent.stats.quarantined} quarantined memories`
        : undefined,
  })
  const brokenTools = agent.toolsData.filter(
    (tool) => tool.access !== "denied" && tool.errorRate !== null && tool.errorRate > 3,
  ).length
  badges.push({
    tab: "tools",
    label: agent.toolsData.length ? `${agent.toolsData.filter((tool) => tool.access !== "denied").length}` : "0",
    tone: brokenTools > 0 ? "warning" : "neutral",
    srLabel: brokenTools > 0 ? `${brokenTools} tools above the error band` : undefined,
  })
  badges.push({
    tab: "cost",
    label: agent.budget ? `${formatAgentMoney(agentBudgetLeftUsd(agent.budget))} left` : "No budget",
    tone: agent.budget ? (agentBudgetSegments(agent.budget).state === "exhausted" ? "destructive" : agentBudgetSegments(agent.budget).state === "low" ? "warning" : "neutral") : "neutral",
  })
  return badges
}

export function agentTabBadge(agent: AgentDetail, tab: AgentTab): AgentTabBadge | null {
  return agentTabBadges(agent).find((badge) => badge.tab === tab) ?? null
}

/** One generated sentence per tab. Never hand-written, never a chart. */
export function agentHeadline(agent: AgentDetail, tab: AgentTab): string {
  const attention = agent.attention.length
  switch (tab) {
    case "overview":
      return attention === 0
        ? "Nothing needs attention."
        : `${attention} ${attention === 1 ? "thing needs" : "things need"} attention.`
    case "runs": {
      const runs = agent.stats.runs
      if (runs === 0) return "No runs in this period."
      const failed = formatAgentPercent(agent.stats.errorRate)
      const retries =
        agent.stats.retriesPerRun !== null && agent.stats.retriesPerRun > agent.retryBand
          ? ` · ${agent.stats.retriesPerRun.toFixed(1)} retries per run (band ≤ ${agent.retryBand.toFixed(1)})`
          : ""
      return `${agentCountLabel(runs)} runs in the ${AGENT_PERIOD_LABEL} · ${failed} failed${retries}.`
    }
    case "sessions":
      if (agent.stats.sessions === 0) return "No sessions yet."
      return agent.stats.activeSessions > 0
        ? `${agentCountLabel(agent.stats.sessions)} sessions · ${agent.stats.activeSessions} live now.`
        : `${agentCountLabel(agent.stats.sessions)} sessions · no live sessions.`
    case "directives":
      if (!agent.directive) return "No directive is set. The agent runs on its base model behaviour."
      return `${agent.directive.name} v${agent.directive.version} is active since ${formatAgentDay(agent.directive.effectiveSince)}.`
    case "policies": {
      if (!agent.policy) return "No policy is set. Only org defaults apply."
      const rules = agent.policy.rules
      const audit = rules.filter((rule) => rule.mode === "audit").length
      return `${agent.policy.name} governs ${rules.length} rules · ${rules.length - audit} enforced · ${audit} in audit mode.`
    }
    case "memories": {
      if (agent.stats.memories === 0) return "No memories yet."
      const base = `${agentCountLabel(agent.stats.memories)} memories · scope: ${agent.memoryScope}`
      return agent.stats.quarantined > 0
        ? `${base} · ${agent.stats.quarantined} waiting for review.`
        : `${base}.`
    }
    case "tools": {
      if (agent.toolsData.length === 0) return "No MCP tools are attached."
      const allowed = agent.toolsData.filter((tool) => tool.access === "allowed").length
      const denied = agent.toolsData.filter((tool) => tool.access === "denied").length
      const broken = agent.toolsData.find(
        (tool) => tool.errorRate !== null && tool.errorRate > 3 && tool.access !== "denied",
      )
      const parts = [`${allowed} ${allowed === 1 ? "tool" : "tools"} allowed`]
      if (denied > 0) parts.push(`${denied} denied`)
      if (broken) parts.push(`${broken.name} above the error band`)
      return `${parts.join(" · ")}.`
    }
    case "cost": {
      if (!agent.budget) return "No spend budget set."
      const segments = agentBudgetSegments(agent.budget)
      const forecast =
        segments.leftUsd > 0 && agent.stats.periodSpendUsd > 0
          ? ""
          : ""
      return `${formatAgentMoney(segments.usedUsd)} of ${formatAgentMoney(segments.totalUsd)} spent this period · ${formatAgentMoney(segments.leftUsd)} left${forecast}.`
    }
    case "audit": {
      if (agent.auditData.length === 0) return "No changes recorded."
      const latest = agent.auditData[0]!
      return `${agentCountLabel(agent.auditTotal || agent.auditData.length)} changes · last by ${latest.actor}, ${formatAgentRelative(latest.at)}.`
    }
  }
}

export function agentHealthSummaryLabel(agent: AgentDetail): string {
  return `${agentHealthLabel(agent.health)} · ${agent.status}`
}

export function agentRetrySignal(agent: AgentDetail): string | null {
  if (agent.stats.retriesPerRun === null) return null
  return `${agent.stats.retriesPerRun.toFixed(1)}/run · band ≤ ${agent.retryBand.toFixed(1)}`
}

export function agentErrorSignal(agent: AgentDetail): string | null {
  if (agent.stats.errorRate === null) return null
  return `${formatAgentPercent(agent.stats.errorRate)} · band ≤ ${formatAgentPercent(agent.errorBandPct)}`
}

export function agentCoverageSignal(agent: AgentDetail): string | null {
  if (agent.stats.coveragePct === null) return null
  return `${formatAgentPercent(agent.stats.coveragePct, 0)} · ${formatAgentCount(agent.stats.coverageRuns)} of ${formatAgentCount(agent.stats.coverageTotal)} runs traced`
}

export function agentTabTitle(tab: AgentTab): string {
  return AGENT_TABS.find((entry) => entry.id === tab)?.label ?? "Overview"
}

export function formatAgentTokens(tokensIn: number, tokensOut: number): string {
  return `${formatAgentCount(tokensIn)} in · ${formatAgentCount(tokensOut)} out`
}

export function agentP95Signal(agent: AgentDetail): string | null {
  if (agent.stats.p95Ms === null) return null
  if (agent.latencyBudgetMs === null) return formatAgentDuration(agent.stats.p95Ms)
  return `${formatAgentDuration(agent.stats.p95Ms)} · budget ${formatAgentDuration(agent.latencyBudgetMs)}`
}

export function agentPct(value: number | null | undefined): string {
  return agentPctLabel(value ?? 0)
}

/** Deep link from an attention reason into the tab and filter that proves it. */
export function agentAttentionHref(item: { agentId: string; tab: AgentTab; filter?: string }, returnTo?: string): string {
  const params = new URLSearchParams()
  if (item.tab !== "overview") params.set("tab", item.tab)
  if (item.filter) {
    for (const [key, value] of new URLSearchParams(item.filter)) params.set(key, value)
  }
  if (returnTo) params.set("return", returnTo)
  const query = params.toString()
  return `/agents/${encodeURIComponent(item.agentId)}${query ? `?${query}` : ""}`
}
