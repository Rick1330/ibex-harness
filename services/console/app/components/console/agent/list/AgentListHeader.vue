<script setup lang="ts">
import { computed } from "vue"
import { Download, FileJson, FileSpreadsheet } from "@lucide/vue"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import ConsolePageHeader from "@/components/console/ConsolePageHeader.vue"
import {
  agentBudgetLeftPct,
  agentBudgetLeftUsd,
  agentStatusCounts,
  type AgentStatus,
  type AgentSummary,
} from "@/lib/agent-preview"
import type { AgentListState } from "@/lib/agent-list-query"

const props = defineProps<{
  state: AgentListState
  records: AgentSummary[]
}>()

const emit = defineEmits<{ status: [status: AgentStatus] }>()

const summary = computed(() => [
  { label: "agents", count: agentStatusCounts.total, status: null },
  { label: "active", count: agentStatusCounts.active, status: "active" as AgentStatus },
  { label: "paused", count: agentStatusCounts.paused, status: "paused" as AgentStatus },
  { label: "suspended", count: agentStatusCounts.suspended, status: "suspended" as AgentStatus },
])

const aboutNotes = [
  {
    lead: "No invented series.",
    body: "Run-volume, spend-over-time and drift charts need GET /v1/agents/{id}/stats, so they show “Not reported yet” instead.",
  },
  {
    lead: "Health is derived, not decorative.",
    body: "One function turns status, budget, error and retry bands, drift, coverage, latency and quarantine into the same answer on this list and on every agent page.",
  },
  {
    lead: "Filtering is local.",
    body: "Search, status and health filtering run only over the recorded design fixtures in this browser.",
  },
]

function downloadText(filename: string, content: string, type: string): void {
  if (!import.meta.client) return
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value)
  return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

function exportCsv(): void {
  const header = [
    "id",
    "name",
    "status",
    "health",
    "environment",
    "owner",
    "agent_version",
    "model",
    "provider",
    "runs",
    "error_rate",
    "p95_ms",
    "budget_total_usd",
    "budget_used_usd",
    "budget_left_usd",
    "trace_coverage_pct",
    "drift",
    "attention",
  ]
  const rows = props.records.map((agent) =>
    [
      agent.id,
      agent.name,
      agent.status,
      agent.health,
      agent.env,
      agent.owner,
      agent.agentVersion,
      agent.model,
      agent.provider,
      agent.stats.runs,
      agent.stats.errorRate,
      agent.stats.p95Ms,
      agent.budget?.totalUsd ?? null,
      agent.budget?.usedUsd ?? null,
      agent.budget ? agentBudgetLeftUsd(agent.budget) : null,
      agent.stats.coveragePct,
      agent.drift,
      agent.attention.map((item) => item.code).join("|"),
    ]
      .map(csvCell)
      .join(","),
  )
  downloadText("ibex-agents-preview.csv", [header.join(","), ...rows].join("\n"), "text/csv;charset=utf-8")
}

function exportJson(): void {
  const rows = props.records.map((agent) => ({
    id: agent.id,
    name: agent.name,
    status: agent.status,
    health: agent.health,
    environment: agent.env,
    owner: agent.owner,
    agent_version: agent.agentVersion,
    model: agent.model,
    provider: agent.provider,
    runs: agent.stats.runs,
    error_rate: agent.stats.errorRate,
    p95_ms: agent.stats.p95Ms,
    budget: agent.budget
      ? {
          total_usd: agent.budget.totalUsd,
          used_usd: agent.budget.usedUsd,
          left_usd: agentBudgetLeftUsd(agent.budget),
          left_pct: agentBudgetLeftPct(agent.budget),
        }
      : null,
    trace_coverage_pct: agent.stats.coveragePct,
    drift: agent.drift,
    attention: agent.attention.map((item) => ({
      code: item.code,
      title: item.title,
      value: item.value,
      threshold: item.threshold,
      tab: item.tab,
    })),
  }))
  downloadText("ibex-agents-preview.json", JSON.stringify(rows, null, 2), "application/json")
}
</script>

<template>
  <ConsolePageHeader
    title="Agents"
    definition="Inventory, health, budget, and drift for every agent in this organization."
    state="illustrative"
    verdict="Twenty-four recorded design fixtures populate this inventory. Agent summary, detail, health, and statistics contracts are not connected, so no row is live organization inventory."
    contract="operator.agents.inventory.v1 [NEEDS-BACKEND]"
    scope="org_demo_42 · all environments"
    range="Last 14 days · top-bar range not applied"
    coverage="0% live · 24 illustrative agents"
    :notes="aboutNotes"
  >
    <template #actions>
      <DropdownMenu>
        <DropdownMenuTrigger as-child>
          <button
            type="button"
            class="ix-button-secondary"
            aria-label="Export agents in this view"
          >
            <Download :size="13" :stroke-width="1.8" aria-hidden="true" />
            Export
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" class="w-56 p-1.5">
          <DropdownMenuLabel class="px-2 py-1 text-[0.6875rem] font-medium text-fg-3">
            {{ records.length }} {{ records.length === 1 ? "agent" : "agents" }} in this view
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="exportCsv">
            <FileSpreadsheet :size="13" :stroke-width="1.8" aria-hidden="true" />
            Export CSV
          </DropdownMenuItem>
          <DropdownMenuItem class="gap-2 py-1.5 text-xs" @select="exportJson">
            <FileJson :size="13" :stroke-width="1.8" aria-hidden="true" />
            Export JSON
          </DropdownMenuItem>
          <p class="px-2 pt-1 pb-1 text-[0.6875rem] leading-4 text-fg-3">
            Exports the current filters and sort, not the whole inventory.
          </p>
        </DropdownMenuContent>
      </DropdownMenu>
    </template>

    <div
      class="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs leading-4 text-fg-3"
      role="group"
      aria-label="Filter by status"
    >
      <span class="mr-1 text-[0.6875rem] font-medium text-fg-3">Status</span>
      <template v-for="(item, index) in summary" :key="item.label">
        <span v-if="index > 0" class="text-fg-off" aria-hidden="true">·</span>
        <span class="inline-flex items-baseline gap-1">
          <template v-if="item.status">
            <button
              type="button"
              class="rounded font-mono text-xs font-medium text-fg-2 tabular-nums underline-offset-2 hover:text-fg-1 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
              :aria-label="`Filter to ${item.count} ${item.label} agents`"
              @click="emit('status', item.status)"
            >
              {{ item.count }}
            </button>
            {{ item.label }}
          </template>
          <template v-else>
            <span class="font-mono text-xs font-medium text-fg-2 tabular-nums">{{ item.count }}</span>
            {{ item.label }}
          </template>
        </span>
      </template>
    </div>
  </ConsolePageHeader>
</template>
