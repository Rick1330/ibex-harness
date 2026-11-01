<script setup lang="ts">
import { computed } from "vue"
import { Search, TriangleAlert } from "@lucide/vue"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import AgentLockedAction from "../../primitives/AgentLockedAction.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import MemoryEmptyValue from "@/components/console/memory/primitives/MemoryEmptyValue.vue"
import { useAgentTabQueryString } from "@/composables/useAgentTabQuery"
import { formatAgentCount, formatAgentRelative } from "@/lib/agent-detail"
import type { AgentDetail } from "@/lib/agent-preview"

const props = defineProps<{ agent: AgentDetail; returnTo: string }>()

const search = useAgentTabQueryString("mq")

const quarantined = computed(() => props.agent.memoriesData.filter((memory) => memory.quarantined))
const filtered = computed(() => {
  const needle = search.value.trim().toLowerCase()
  if (!needle) return props.agent.memoriesData
  return props.agent.memoriesData.filter(
    (memory) => `${memory.preview} ${memory.category} ${memory.labels.join(" ")} ${memory.id}`.toLowerCase().includes(needle),
  )
})

const scopeNote = computed(() => {
  switch (props.agent.memoryScope) {
    case "agent":
      return "Agent scope: memories are shared across all sessions of this agent, not other agents."
    case "org":
      return "Org scope: memories are shared across every agent in this organization."
    default:
      return "Session scope: memories stay inside the session that wrote them."
  }
})
</script>

<template>
  <div class="min-w-0 space-y-5">
    <p class="flex items-start gap-2 text-xs leading-4 text-fg-3">
      <TriangleAlert v-if="agent.stats.quarantined" :size="13" :stroke-width="1.9" class="mt-0.5 shrink-0 text-warn" aria-hidden="true" />
      <span>{{ scopeNote }}</span>
    </p>

    <section v-if="quarantined.length" aria-labelledby="memories-quarantine" class="rounded-lg border border-line-subtle bg-surface">
      <div class="flex flex-wrap items-baseline justify-between gap-2 p-4 pb-2">
        <h2 id="memories-quarantine" class="text-sm leading-5 font-semibold text-warn">Quarantined for review</h2>
        <span class="font-mono text-xs text-fg-3 tabular-nums">{{ quarantined.length }}</span>
      </div>
      <ul class="divide-y divide-line-subtle border-t border-line-subtle">
        <li v-for="memory in quarantined" :key="memory.id" class="p-4">
          <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
            <div class="min-w-0 flex-1">
              <NuxtLink
                :to="memory.href"
                class="line-clamp-2 text-[0.8125rem] leading-5 font-medium text-fg-1 underline decoration-transparent underline-offset-3 transition-colors hover:text-accent-memory hover:decoration-accent-memory"
              >
                {{ memory.preview }}
              </NuxtLink>
              <p class="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-fg-3">
                <span class="font-mono">{{ memory.id }}</span>
                <template v-if="memory.sessionId">
                  <span aria-hidden="true">·</span>
                  <NuxtLink :to="`/sessions/${encodeURIComponent(memory.sessionId)}`" class="font-mono underline decoration-line-strong underline-offset-3 hover:text-accent-memory">
                    {{ memory.sessionId }}
                  </NuxtLink>
                </template>
                <span aria-hidden="true">·</span>
                <span>{{ memory.lastUsedAt ? formatAgentRelative(memory.lastUsedAt) : "never used" }}</span>
              </p>
            </div>
            <div class="flex shrink-0 items-center gap-2">
              <span v-if="memory.injectionRisk !== null" class="flex w-40 items-center gap-2">
                <span class="text-[0.6875rem] text-fg-3">Injection</span>
                <MemoryScoreBar :value="memory.injectionRisk" color="bg-warn" :label="`Injection risk ${memory.injectionRisk.toFixed(2)}`" />
                <span class="font-mono text-xs text-warn tabular-nums">{{ memory.injectionRisk.toFixed(2) }}</span>
              </span>
              <AgentLockedAction label="Release" size="sm" />
              <AgentLockedAction label="Delete" size="sm" variant="destructive" />
            </div>
          </div>
        </li>
      </ul>
    </section>

    <div class="flex flex-wrap items-center gap-2">
      <div class="relative min-w-48 flex-1 sm:max-w-64">
        <Search :size="13" :stroke-width="1.9" class="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-fg-3" aria-hidden="true" />
        <input v-model="search" type="search" placeholder="Search memories" aria-label="Search memories" class="ix-input h-8 pl-8 text-xs" >
      </div>
      <span class="ml-auto text-xs text-fg-3">{{ filtered.length }} of {{ agent.memoriesData.length }} shown</span>
    </div>

    <div class="overflow-hidden rounded-lg border border-line-subtle bg-surface-1">
      <div class="overflow-x-auto">
        <table class="ix-table" aria-label="Agent memories">
          <thead>
            <tr>
              <th scope="col">Memory</th>
              <th scope="col" class="w-36">Category</th>
              <th scope="col" class="w-24">Lifecycle</th>
              <th scope="col" class="w-36">Confidence</th>
              <th scope="col" class="w-20 text-right">Retrievals</th>
              <th scope="col" class="w-24">Last used</th>
              <th scope="col" class="w-36">Extracted from</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="memory in filtered" :key="memory.id" :class="memory.quarantined && 'quarantine-row'">
              <td>
                <NuxtLink
                  :to="memory.href"
                  class="block max-w-96 truncate text-[0.8125rem] text-fg-1 underline decoration-transparent underline-offset-3 transition-colors hover:text-accent-memory hover:decoration-accent-memory"
                >
                  {{ memory.preview }}
                </NuxtLink>
              </td>
              <td class="text-xs text-fg-2">
                {{ memory.category }}
                <span v-if="memory.labels.length" class="font-mono text-[0.625rem] text-fg-3"> · {{ memory.labels.join(", ") }}</span>
              </td>
              <td>
                <span class="text-xs" :class="memory.quarantined ? 'text-warn' : 'text-fg-3'">{{ memory.lifecycle }}</span>
              </td>
              <td>
                <span class="flex items-center gap-2">
                  <MemoryScoreBar :value="memory.confidence" label="Confidence" class="w-16" />
                  <span class="font-mono text-xs text-fg-1 tabular-nums">{{ memory.confidence.toFixed(2) }}</span>
                </span>
              </td>
              <td class="text-right font-mono text-xs text-fg-1 tabular-nums">{{ formatAgentCount(memory.retrievals) }}</td>
              <td>
                <Tooltip v-if="memory.lastUsedAt" :delay-duration="150">
                  <TooltipTrigger as-child>
                    <span class="cursor-default text-xs whitespace-nowrap text-fg-2">{{ formatAgentRelative(memory.lastUsedAt) }}</span>
                  </TooltipTrigger>
                  <TooltipContent side="top" class="!text-xs">{{ memory.lastUsedAt }}</TooltipContent>
                </Tooltip>
                <span v-else class="text-xs text-fg-off">never</span>
              </td>
              <td>
                <NuxtLink
                  v-if="memory.sessionId"
                  :to="`/sessions/${encodeURIComponent(memory.sessionId)}`"
                  class="font-mono text-xs text-fg-2 underline decoration-transparent underline-offset-3 hover:text-accent-memory hover:decoration-accent-memory"
                >
                  {{ memory.sessionId }}
                </NuxtLink>
                <MemoryEmptyValue v-else />
              </td>
            </tr>
            <tr v-if="!filtered.length">
              <td colspan="7" class="!h-24 text-center text-xs text-fg-3">No memories match this search.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <p class="text-xs leading-4 text-fg-3">
      Pin and flag actions require a privileged write contract and are disabled in this read-only console.
    </p>
  </div>
</template>

<style scoped>
.quarantine-row {
  box-shadow: inset 3px 0 0 var(--row-attention-edge);
}
</style>
