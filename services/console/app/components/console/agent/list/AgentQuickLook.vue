<script setup lang="ts">
import { computed } from "vue"
import { ArrowUpRight, CircleSlash } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import AgentAttentionItem from "../primitives/AgentAttentionItem.vue"
import AgentBudgetBar from "../primitives/AgentBudgetBar.vue"
import AgentEnvTag from "../primitives/AgentEnvTag.vue"
import AgentHealthDot from "../primitives/AgentHealthDot.vue"
import AgentStatusPill from "../primitives/AgentStatusPill.vue"
import AgentVersionTag from "../primitives/AgentVersionTag.vue"
import { formatAgentCount, formatAgentMoney, formatAgentPercent, formatAgentRelative, formatAgentStamp } from "@/lib/agent-detail"
import { AGENT_ERROR_BAND_PCT, agentBudgetLeftPct, agentBudgetLeftUsd, agentProviderLabel, getAgentPreview } from "@/lib/agent-preview"
import BrandIcon from "@/components/console/BrandIcon.vue"

const props = defineProps<{
  agentId: string
  returnTo: string
}>()

const emit = defineEmits<{ open: [] }>()

const agent = computed(() => getAgentPreview(props.agentId))
const detail = computed(() => agent.value)
const lastRuns = computed(() => (agent.value ? agent.value.runsData.slice(0, 5) : []))
const topAttention = computed(() => (agent.value ? agent.value.attention.slice(0, 3) : []))

const kpis = computed(() => {
  const agentValue = agent.value
  if (!agentValue) return []
  const budget = agentValue.budget
  return [
    {
      label: "Last run",
      value: agentValue.stats.lastRun ? formatAgentRelative(agentValue.stats.lastRun.at) : "Never",
      over: agentValue.stats.lastRun?.status === "failed",
    },
    {
      label: "Error rate",
      value: agentValue.stats.errorRate === null ? "—" : formatAgentPercent(agentValue.stats.errorRate),
      over: (agentValue.stats.errorRate ?? 0) > AGENT_ERROR_BAND_PCT,
    },
    {
      label: "p95",
      value: agentValue.stats.p95Ms === null ? "—" : `${(agentValue.stats.p95Ms / 1000).toFixed(1)}s`,
      over: agentValue.latencyBudgetMs !== null && (agentValue.stats.p95Ms ?? 0) > agentValue.latencyBudgetMs,
    },
    {
      label: "Budget left",
      value: budget ? formatAgentMoney(agentBudgetLeftUsd(budget)) : "Not set",
      over: budget ? agentBudgetLeftUsd(budget) <= 0 || agentBudgetLeftPct(budget) < budget.floorPct : false,
    },
    { label: "Sessions", value: formatAgentCount(agentValue.stats.sessions), over: false },
    { label: "Memories", value: formatAgentCount(agentValue.stats.memories), over: agentValue.stats.quarantined > 0 },
  ]
})
</script>

<template>
  <div v-if="detail" class="flex min-h-0 flex-col gap-5 p-5 pt-2">
    <div class="min-w-0">
      <div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5">
        <h2 class="min-w-0 truncate text-lg leading-6 font-semibold text-fg-1">{{ detail.name }}</h2>
        <AgentHealthDot :health="detail.health" :reasons="detail.healthReasons" />
        <AgentStatusPill :status="detail.status" />
      </div>
      <p class="mt-1 line-clamp-2 text-xs leading-4 text-fg-3">{{ detail.description }}</p>
      <p class="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-fg-3">
        <AgentVersionTag label="Agent" :value="`v${detail.agentVersion}`" />
        <span aria-hidden="true">·</span>
        <span class="inline-flex items-center gap-1.5 font-mono text-[0.6875rem]">
          <BrandIcon :id="detail.provider" :size="12" :label="`${agentProviderLabel(detail.provider)} logo`" />
          {{ detail.model }}
        </span>
        <span aria-hidden="true">·</span>
        <AgentEnvTag :env="detail.env" />
        <span aria-hidden="true">·</span>
        <span>{{ detail.owner }}</span>
      </p>
    </div>

    <div class="grid grid-cols-2 gap-2">
      <div v-for="kpi in kpis" :key="kpi.label" class="rounded-lg border border-line-subtle bg-surface-1 px-3 py-2">
        <p class="text-[0.6875rem] leading-3.5 text-fg-3">{{ kpi.label }}</p>
        <p class="mt-0.5 font-mono text-sm leading-5 font-semibold tabular-nums" :class="kpi.over ? 'text-warn' : 'text-fg-1'">
          {{ kpi.value }}
        </p>
      </div>
    </div>

    <div v-if="detail.budget">
      <p class="mb-1.5 text-xs font-medium text-fg-3">Spend budget</p>
      <AgentBudgetBar :budget="detail.budget" size="md" show-label show-percent />
    </div>

    <div v-if="topAttention.length">
      <p class="mb-1.5 text-xs font-medium text-warn">Needs attention</p>
      <ul class="flex flex-col gap-1.5">
        <li v-for="item in topAttention" :key="item.id">
          <AgentAttentionItem
            :item="item"
            :show-agent="false"
            compact
            :href="`/agents/${encodeURIComponent(detail.id)}?tab=${item.tab}&return=${encodeURIComponent(returnTo)}`"
          />
        </li>
      </ul>
    </div>

    <div>
      <p class="mb-1.5 text-xs font-medium text-fg-3">Last runs</p>
      <ul v-if="lastRuns.length" class="flex flex-col divide-y divide-line-subtle rounded-lg border border-line-subtle bg-surface-1">
        <li v-for="run in lastRuns" :key="run.id" class="flex items-center gap-2.5 px-3 py-2">
          <CircleSlash v-if="run.status === 'failed'" :size="12" :stroke-width="2" class="shrink-0 text-crit" aria-hidden="true" />
          <span v-else class="size-2 shrink-0 rounded-full bg-ok" aria-hidden="true" />
          <span class="min-w-0 flex-1 truncate font-mono text-xs text-fg-2">{{ run.id }}</span>
          <span class="font-mono text-[0.6875rem] text-fg-3 tabular-nums">{{ (run.durationMs / 1000).toFixed(1) }}s</span>
          <Tooltip :delay-duration="150">
            <TooltipTrigger as-child>
              <span class="shrink-0 text-[0.6875rem] text-fg-3">{{ formatAgentRelative(run.startedAt) }}</span>
            </TooltipTrigger>
            <TooltipContent side="top" class="!font-mono !text-xs">{{ formatAgentStamp(run.startedAt) }}</TooltipContent>
          </Tooltip>
        </li>
      </ul>
      <p v-else class="rounded-lg border border-dashed border-line px-3 py-3 text-xs text-fg-3">
        This agent has never run.
      </p>
    </div>

    <NuxtLink
      :to="`/agents/${encodeURIComponent(detail.id)}?return=${encodeURIComponent(returnTo)}`"
      :aria-label="`Open ${detail.name}`"
      class="ix-button-primary mt-auto h-9 w-full gap-1.5 text-xs"
      @click="emit('open')"
    >
      Open agent
      <ArrowUpRight :size="13" :stroke-width="1.9" aria-hidden="true" />
    </NuxtLink>
  </div>
</template>
