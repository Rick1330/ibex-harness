<script setup lang="ts">
import { computed } from "vue"
import { ArrowRight, CircleAlert, CircleSlash, TriangleAlert } from "@lucide/vue"
import type { AgentAttentionItem } from "@/lib/agent-preview"
import { formatAgentRelative } from "@/lib/agent-detail"

const props = withDefaults(
  defineProps<{
    item: AgentAttentionItem
    /** The strip hides the agent name because the row already names it. */
    showAgent?: boolean
    compact?: boolean
    /** Resolved by the parent, because the target tab lives on the detail page. */
    href?: string
  }>(),
  { showAgent: true, compact: false, href: undefined },
)

const config = computed(() => {
  if (props.item.severity === "critical") {
    return { icon: CircleSlash, tone: "text-crit", word: "Failing" }
  }
  if (props.item.severity === "warning") {
    return { icon: TriangleAlert, tone: "text-warn", word: "Needs attention" }
  }
  return { icon: CircleAlert, tone: "text-fg-3", word: "Info" }
})
</script>

<template>
  <div class="flex min-w-0 items-center gap-2 text-xs leading-4" :class="compact && 'gap-1.5'">
    <component :is="config.icon" :size="compact ? 12 : 13" :stroke-width="1.9" class="shrink-0" :class="config.tone" aria-hidden="true" />
    <span class="sr-only">{{ config.word }}:</span>
    <span class="min-w-0 truncate text-fg-2">
      <NuxtLink
        v-if="showAgent"
        :to="`/agents/${encodeURIComponent(item.agentId)}`"
        class="font-medium text-fg-1 underline-offset-2 hover:underline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
      >
        {{ item.agentName }}
      </NuxtLink>
      <span v-if="showAgent" class="text-fg-3"> · </span>
      <span>{{ item.title }}</span>
      <span v-if="!compact" class="font-mono text-fg-3 tabular-nums">
        · {{ item.value }} · {{ item.threshold }}
      </span>
    </span>
    <span class="hidden shrink-0 font-mono text-[0.6875rem] text-fg-3 tabular-nums sm:inline">
      {{ formatAgentRelative(item.at) }}
    </span>
    <NuxtLink
      v-if="href"
      :to="href"
      class="ml-auto inline-flex shrink-0 items-center gap-0.5 rounded text-[0.6875rem] font-medium text-fg-2 transition-colors hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent-memory"
      :aria-label="`View ${item.agentName}: ${item.title}`"
    >
      View
      <ArrowRight :size="11" :stroke-width="2" aria-hidden="true" />
    </NuxtLink>
  </div>
</template>
