<script setup lang="ts">
import { computed } from "vue"
import AgentBudgetBar from "../../primitives/AgentBudgetBar.vue"
import AgentLockedAction from "../../primitives/AgentLockedAction.vue"
import AgentPendingData from "../../primitives/AgentPendingData.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import { agentBudgetSegments, formatAgentCount, formatAgentMoney, formatAgentPercent, formatAgentRelative } from "@/lib/agent-detail"
import type { AgentDetail } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail }>()

const segments = computed(() => (props.agent.budget ? agentBudgetSegments(props.agent.budget) : null))

const spendTotal = computed(() =>
  props.agent.spendByModel.reduce((sum, slice) => sum + slice.usd, 0) ||
  props.agent.spendByTool.reduce((sum, slice) => sum + slice.usd, 0),
)

const spendByModel = computed(() =>
  [...props.agent.spendByModel].sort((first, second) => second.usd - first.usd).map((slice) => ({
    ...slice,
    pct: spendTotal.value > 0 ? (slice.usd / spendTotal.value) * 100 : 0,
  })),
)

const spendByTool = computed(() =>
  [...props.agent.spendByTool].sort((first, second) => second.usd - first.usd).map((slice) => ({
    ...slice,
    pct: spendTotal.value > 0 ? (slice.usd / spendTotal.value) * 100 : 0,
  })),
)

const tokensPerRun = computed(() =>
  props.agent.stats.runs > 0 ? (props.agent.stats.tokensIn + props.agent.stats.tokensOut) / props.agent.stats.runs : null,
)
</script>

<template>
  <div class="min-w-0 space-y-6">
    <section v-if="segments" aria-labelledby="cost-budget" class="rounded-lg border border-line-subtle bg-surface-1 p-5">
      <div class="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="cost-budget" class="text-sm leading-5 font-semibold text-fg-1">Spend budget</h2>
        <div class="flex items-center gap-2.5">
          <span class="text-xs text-fg-3">Resets {{ formatAgentRelative(agent.budget!.resetAt) }}</span>
          <AgentLockedAction label="Edit budget" size="sm" />
        </div>
      </div>
      <div class="mt-3 max-w-2xl">
        <AgentBudgetBar :budget="agent.budget!" size="lg" show-label show-percent />
      </div>
      <p class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs leading-4 text-fg-3">
        <span>
          At 100%: {{ agent.budget!.onExhausted === "block" ? "new runs are blocked" : "alert only" }}
        </span>
        <span aria-hidden="true">·</span>
        <span>Committed is reserved but not yet spent; it is shown as its own bar segment.</span>
      </p>
    </section>

    <div v-else class="rounded-lg border border-dashed border-line px-5 py-6 text-center">
      <p class="text-sm font-medium text-fg-1">No spend budget set</p>
      <p class="mt-1 text-xs text-fg-3">Lifetime totals below are shipped; there is no period budget for this agent.</p>
    </div>

    <div class="grid gap-6 xl:grid-cols-2">
      <section aria-labelledby="cost-model" class="rounded-lg border border-line-subtle bg-surface-1 p-5">
        <h2 id="cost-model" class="text-sm leading-5 font-semibold text-fg-1">Spend by model</h2>
        <ul class="mt-3 flex flex-col gap-2.5">
          <li v-for="slice in spendByModel" :key="slice.label" class="flex items-center gap-3 text-xs">
            <span class="w-36 shrink-0 truncate font-mono text-fg-2">{{ slice.label }}</span>
            <MemoryScoreBar :value="slice.pct / 100" color="bg-viz-2" :label="`${slice.label} share`" />
            <span class="w-24 shrink-0 text-right font-mono text-fg-1 tabular-nums">{{ formatAgentMoney(slice.usd) }}</span>
            <span class="w-10 shrink-0 text-right font-mono text-fg-3 tabular-nums">{{ formatAgentPercent(slice.pct, 0) }}</span>
          </li>
        </ul>
        <p v-if="!spendByModel.length" class="mt-2 text-xs text-fg-3">No per-model breakdown recorded.</p>
      </section>

      <section aria-labelledby="cost-tools" class="rounded-lg border border-line-subtle bg-surface-1 p-5">
        <h2 id="cost-tools" class="text-sm leading-5 font-semibold text-fg-1">Spend by tool</h2>
        <ul class="mt-3 flex flex-col gap-2.5">
          <li v-for="slice in spendByTool" :key="slice.label" class="flex items-center gap-3 text-xs">
            <span class="w-36 shrink-0 truncate font-mono text-fg-2">{{ slice.label }}</span>
            <MemoryScoreBar :value="slice.pct / 100" color="bg-viz-3" :label="`${slice.label} share`" />
            <span class="w-24 shrink-0 text-right font-mono text-fg-1 tabular-nums">{{ formatAgentMoney(slice.usd) }}</span>
            <span class="w-10 shrink-0 text-right font-mono text-fg-3 tabular-nums">{{ formatAgentPercent(slice.pct, 0) }}</span>
          </li>
        </ul>
        <p v-if="!spendByTool.length" class="mt-2 text-xs text-fg-3">No per-tool breakdown recorded.</p>
      </section>
    </div>

    <section aria-labelledby="cost-tokens" class="rounded-lg border border-line-subtle bg-surface-1 p-5">
      <h2 id="cost-tokens" class="text-sm leading-5 font-semibold text-fg-1">Tokens</h2>
      <div class="mt-3 grid gap-4 sm:grid-cols-2">
        <div>
          <p class="text-xs text-fg-3">Lifetime</p>
          <p class="mt-0.5 font-mono text-sm font-semibold text-fg-1 tabular-nums">
            {{ formatAgentCount(agent.stats.tokensIn) }} in · {{ formatAgentCount(agent.stats.tokensOut) }} out
          </p>
        </div>
        <div>
          <p class="flex items-center gap-1 text-xs text-fg-3">
            Context budget per run
            <MemoryInfoHint label="Context budget">
              <p class="font-medium text-fg-1">Context budget</p>
              <p class="mt-1">
                Average tokens per run compared with the configured context budget of
                {{ formatAgentCount(agent.contextBudgetTokens) }} tokens.
              </p>
            </MemoryInfoHint>
          </p>
          <div class="mt-1.5 flex items-center gap-2">
            <MemoryScoreBar
              v-if="tokensPerRun !== null"
              :value="tokensPerRun / agent.contextBudgetTokens"
              color="bg-viz-2"
              :label="`Average tokens per run vs budget`"
              class="max-w-48"
            />
            <span v-if="tokensPerRun !== null" class="font-mono text-xs text-fg-1 tabular-nums">
              {{ formatAgentCount(Math.round(tokensPerRun)) }} avg · {{ formatAgentCount(agent.contextBudgetTokens) }} budget
            </span>
            <span v-else class="text-xs text-fg-3">Not reported yet</span>
          </div>
        </div>
      </div>
    </section>

    <AgentPendingData
      title="Spend over time"
      contract="GET /v1/agents/{id}/stats"
      description="A real daily spend chart with the budget pace line draws here once per-period data ships."
    />

    <section aria-labelledby="cost-alerts" class="rounded-lg border border-line-subtle bg-surface-1 p-5">
      <div class="flex items-baseline justify-between gap-2">
        <h2 id="cost-alerts" class="text-sm leading-5 font-semibold text-fg-1">Alerts</h2>
        <AgentLockedAction label="Edit alerts" size="sm" />
      </div>
      <ul class="mt-2 divide-y divide-line-subtle">
        <li v-for="alert in agent.alerts" :key="alert.threshold" class="flex items-baseline justify-between gap-3 py-2 text-xs">
          <span class="font-mono text-fg-2 tabular-nums">{{ alert.threshold }}% of budget</span>
          <span class="text-fg-3">
            notifies {{ alert.notify }}
            <template v-if="alert.lastFiredAt"> · fired {{ formatAgentRelative(alert.lastFiredAt) }}</template>
            <template v-else> · never fired</template>
          </span>
        </li>
      </ul>
      <p v-if="!agent.alerts.length" class="mt-2 text-xs text-fg-3">No alert thresholds recorded.</p>
    </section>

    <p class="flex items-center gap-1.5 text-xs leading-4 text-fg-3">
      Lifetime totals are shipped. Per-period series are pending.
      <MemoryInfoHint label="Why?">
        <p class="font-medium text-fg-1">Deferred metrics</p>
        <p class="mt-1">
          The deferred stats endpoint has not shipped, so no per-period chart, trend or forecast is drawn. Only recorded
          totals are shown.
        </p>
      </MemoryInfoHint>
    </p>
  </div>
</template>
