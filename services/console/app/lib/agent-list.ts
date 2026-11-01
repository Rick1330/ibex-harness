import {
  agentBudgetLeftPct,
  agentHealthLabel,
  agentStatusLabel,
  healthRank,
  type AgentHealthState,
  type AgentSummary,
} from "./agent-preview"
import type {
  AgentGroupKey,
  AgentListState,
  AgentSortDirection,
  AgentSortKey,
  AgentView,
} from "./agent-list-query"
import { AGENT_VIEW_LABELS } from "./agent-list-query"

export function agentMatchesSearch(agent: AgentSummary, search: string): boolean {
  const needle = search.trim().toLowerCase()
  if (!needle) return true
  const haystack = [agent.name, agent.id, agent.owner, agent.model, agent.provider, agent.env, ...agent.tags]
    .join(" ")
    .toLowerCase()
  return haystack.includes(needle)
}

export function agentNeedsAttention(agent: AgentSummary): boolean {
  return agent.health === "failing" || agent.health === "attention"
}

export function agentIsNearBudget(agent: AgentSummary): boolean {
  if (!agent.budget) return false
  return agentBudgetLeftPct(agent.budget) < agent.budget.floorPct
}

export function viewMatchesAgent(agent: AgentSummary, view: AgentView): boolean {
  switch (view) {
    case "attention":
      return agentNeedsAttention(agent)
    case "budget":
      return agentIsNearBudget(agent)
    case "drifted":
      return agent.drift === "drifted" || agent.drift === "watch"
    case "paused":
      return agent.status === "paused" || agent.status === "draining"
    default:
      return true
  }
}

export function filterAgents(agents: AgentSummary[], state: AgentListState): AgentSummary[] {
  return agents.filter((agent) => {
    if (!agentMatchesSearch(agent, state.search)) return false
    if (!viewMatchesAgent(agent, state.view)) return false
    if (state.statuses.length && !state.statuses.includes(agent.status)) return false
    if (state.envs.length && !state.envs.includes(agent.env)) return false
    if (state.models.length && !state.models.includes(agent.model)) return false
    if (state.owners.length && !state.owners.includes(agent.owner)) return false
    if (state.healths.length && !state.healths.includes(agent.health)) return false
    const showsNoData = state.includeNoData || state.view === "paused" || state.healths.includes("no_data")
    if (!showsNoData && agent.stats.runs === 0) return false
    return true
  })
}

function compareNumbers(
  first: number | null,
  second: number | null,
  direction: AgentSortDirection,
): number {
  if (first === null && second === null) return 0
  if (first === null) return 1
  if (second === null) return -1
  return direction === "asc" ? first - second : second - first
}

function compareLastRun(first: AgentSummary, second: AgentSummary, direction: AgentSortDirection): number {
  const left = first.stats.lastRun ? Date.parse(first.stats.lastRun.at) : null
  const right = second.stats.lastRun ? Date.parse(second.stats.lastRun.at) : null
  return compareNumbers(left, right, direction)
}

export function sortAgents(
  agents: AgentSummary[],
  sort: AgentSortKey,
  direction: AgentSortDirection,
): AgentSummary[] {
  return [...agents].sort((first, second) => {
    let primary = 0
    switch (sort) {
      case "health": {
        primary = healthRank(first.health) - healthRank(second.health)
        if (direction === "desc") primary *= -1
        break
      }
      case "name":
        primary = first.name.localeCompare(second.name)
        break
      case "owner":
        primary = first.owner.localeCompare(second.owner)
        break
      case "runs":
        primary = compareNumbers(first.stats.runs, second.stats.runs, direction)
        break
      case "errors":
        primary = compareNumbers(first.stats.errorRate, second.stats.errorRate, direction)
        break
      case "p95":
        primary = compareNumbers(first.stats.p95Ms, second.stats.p95Ms, direction)
        break
      case "budget":
        primary = compareNumbers(
          first.budget ? agentBudgetLeftPct(first.budget) : null,
          second.budget ? agentBudgetLeftPct(second.budget) : null,
          direction,
        )
        break
      case "coverage":
        primary = compareNumbers(first.stats.coveragePct, second.stats.coveragePct, direction)
        break
      case "lastRun":
        primary = compareLastRun(first, second, direction)
        break
    }
    if (primary !== 0) return primary
    // Stable, meaningful tiebreak: the busiest agent first, then name.
    if (second.stats.runs !== first.stats.runs) return second.stats.runs - first.stats.runs
    return first.name.localeCompare(second.name)
  })
}

export function sortAgentAttention(agents: AgentSummary[]): AgentSummary[] {
  return sortAgents(agents, "health", "asc")
}

export type AgentGroup = {
  key: string
  label: string
  agents: AgentSummary[]
  attentionCount: number
  meta?: string
}

function healthGroupOrder(health: AgentHealthState): number {
  return healthRank(health)
}

export function groupAgents(agents: AgentSummary[], group: AgentGroupKey): AgentGroup[] {
  if (group === "none") {
    return [
      {
        key: "all",
        label: "All agents",
        agents,
        attentionCount: agents.filter(agentNeedsAttention).length,
      },
    ]
  }

  const buckets = new Map<string, AgentSummary[]>()
  for (const agent of agents) {
    const key = group === "owner" ? agent.owner : group === "env" ? agent.env : agent.health
    const bucket = buckets.get(key) ?? []
    bucket.push(agent)
    buckets.set(key, bucket)
  }

  const entries = [...buckets.entries()].map(([key, rows]) => ({
    key,
    label: group === "health" ? agentHealthLabel(key as AgentHealthState) : key,
    rows,
    order:
      group === "health"
        ? healthGroupOrder(key as AgentHealthState)
        : key === "production"
          ? 0
          : key === "staging"
            ? 1
            : 2,
  }))

  entries.sort((first, second) => first.order - second.order || first.label.localeCompare(second.label))

  return entries.map((entry) => ({
    key: entry.key,
    label: entry.label,
    agents: entry.rows,
    attentionCount: entry.rows.filter(agentNeedsAttention).length,
  }))
}

export function agentViewCounts(agents: AgentSummary[]): Record<AgentView, number> {
  return {
    all: agents.length,
    attention: agents.filter(agentNeedsAttention).length,
    budget: agents.filter(agentIsNearBudget).length,
    drifted: agents.filter((agent) => agent.drift === "drifted" || agent.drift === "watch").length,
    paused: agents.filter((agent) => agent.status === "paused" || agent.status === "draining").length,
  }
}

export type AgentFilterChip = {
  key: string
  field: string
  value: string
  next: AgentListState
}

function without<T>(list: T[], value: T): T[] {
  return list.filter((entry) => entry !== value)
}

export function activeAgentFilterChips(state: AgentListState): AgentFilterChip[] {
  const chips: AgentFilterChip[] = []
  for (const status of state.statuses) {
    chips.push({
      key: `status:${status}`,
      field: "Status",
      value: agentStatusLabel(status),
      next: { ...state, statuses: without(state.statuses, status) },
    })
  }
  for (const env of state.envs) {
    chips.push({
      key: `env:${env}`,
      field: "Environment",
      value: env,
      next: { ...state, envs: without(state.envs, env) },
    })
  }
  for (const model of state.models) {
    chips.push({
      key: `model:${model}`,
      field: "Model",
      value: model,
      next: { ...state, models: without(state.models, model) },
    })
  }
  for (const owner of state.owners) {
    chips.push({
      key: `owner:${owner}`,
      field: "Owner",
      value: owner,
      next: { ...state, owners: without(state.owners, owner) },
    })
  }
  for (const health of state.healths) {
    chips.push({
      key: `health:${health}`,
      field: "Health",
      value: agentHealthLabel(health),
      next: { ...state, healths: without(state.healths, health) },
    })
  }
  if (state.view !== "all") {
    chips.push({
      key: `view:${state.view}`,
      field: "View",
      value: AGENT_VIEW_LABELS[state.view],
      next: { ...state, view: "all" },
    })
  }
  if (state.includeNoData) {
    chips.push({
      key: "all",
      field: "Scope",
      value: "Including agents without data",
      next: { ...state, includeNoData: false },
    })
  }
  return chips
}

export function activeAgentFilterCount(state: AgentListState): number {
  return (
    state.statuses.length +
    state.envs.length +
    state.models.length +
    state.owners.length +
    state.healths.length +
    (state.view !== "all" ? 1 : 0) +
    (state.includeNoData ? 1 : 0)
  )
}

export function agentListIsModified(state: AgentListState): boolean {
  return activeAgentFilterCount(state) > 0 || state.search.trim().length > 0
}

export function agentRowEdge(agent: AgentSummary): "critical" | "warning" | null {
  if (agent.health === "failing") return "critical"
  if (agent.health === "attention") return "warning"
  return null
}

export function agentOptions(agents: AgentSummary[]): {
  models: { value: string; count: number }[]
  owners: { value: string; count: number }[]
} {
  const models = new Map<string, number>()
  const owners = new Map<string, number>()
  for (const agent of agents) {
    models.set(agent.model, (models.get(agent.model) ?? 0) + 1)
    owners.set(agent.owner, (owners.get(agent.owner) ?? 0) + 1)
  }
  const toRows = (map: Map<string, number>) =>
    [...map.entries()]
      .map(([value, count]) => ({ value, count }))
      .sort((first, second) => first.value.localeCompare(second.value))
  return { models: toRows(models), owners: toRows(owners) }
}
