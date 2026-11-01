<script setup lang="ts">
import { computed } from "vue"
import type { AgentBudget } from "@/lib/agent-preview"
import { agentBudgetSegments, formatAgentMoney, formatAgentPercent } from "@/lib/agent-detail"

const props = withDefaults(
  defineProps<{
    budget: AgentBudget
    size?: "sm" | "md" | "lg"
    /** Show the "$x of $y · $z left" line under the bar. */
    showLabel?: boolean
    showPercent?: boolean
  }>(),
  { size: "md", showLabel: true, showPercent: false },
)

const segments = computed(() => agentBudgetSegments(props.budget))
const usedTone = computed(() => {
  if (segments.value.state === "exhausted") return "bg-crit"
  if (segments.value.state === "low") return "bg-warn"
  return "bg-fg-3"
})
const height = computed(() => (props.size === "sm" ? "h-1" : props.size === "lg" ? "h-2.5" : "h-1.5"))
const floorTick = computed(() => Math.min(100, Math.max(0, 100 - segments.value.floorPct)))
const label = computed(
  () =>
    `Spend budget: ${formatAgentMoney(segments.value.usedUsd)} of ${formatAgentMoney(segments.value.totalUsd)} used, ` +
    `${formatAgentMoney(segments.value.leftUsd)} left (${formatAgentPercent(segments.value.leftPct, 0)}). Floor ${segments.value.floorPct}%.`,
)
</script>

<template>
  <div class="min-w-0">
    <div
      class="relative w-full overflow-hidden rounded-full bg-raised"
      :class="height"
      role="img"
      :aria-label="label"
    >
      <span
        class="absolute inset-y-0 left-0 transition-[width] duration-200 ease-out motion-reduce:transition-none"
        :class="usedTone"
        :style="{ width: `${Math.min(100, segments.usedPct)}%` }"
      />
      <span
        v-if="segments.committedPct > 0"
        class="absolute inset-y-0 bg-fg-off/50 transition-[width] duration-200 ease-out motion-reduce:transition-none"
        :style="{ left: `${Math.min(100, segments.usedPct)}%`, width: `${Math.min(100 - segments.usedPct, segments.committedPct)}%` }"
      />
      <span
        class="absolute inset-y-0 w-px bg-fg-1/70"
        :style="{ left: `${floorTick}%` }"
        :title="`Floor ${segments.floorPct}% left`"
        aria-hidden="true"
      />
    </div>
    <div v-if="showLabel" class="mt-1 flex flex-wrap items-baseline justify-between gap-x-2 text-[0.6875rem] leading-3.5">
      <span class="font-mono text-fg-2 tabular-nums">
        {{ formatAgentMoney(segments.usedUsd) }} of {{ formatAgentMoney(segments.totalUsd) }}
      </span>
      <span
        class="font-mono tabular-nums"
        :class="segments.state === 'exhausted' ? 'text-crit' : segments.state === 'low' ? 'text-warn' : 'text-fg-3'"
      >
        {{ formatAgentMoney(segments.leftUsd) }} left<template v-if="showPercent"> · {{ formatAgentPercent(segments.leftPct, 0) }}</template>
      </span>
    </div>
    <p v-if="showLabel && segments.committedUsd > 0" class="mt-0.5 text-[0.6875rem] leading-3.5 text-fg-3">
      Includes {{ formatAgentMoney(segments.committedUsd) }} committed but not yet spent.
    </p>
  </div>
</template>
