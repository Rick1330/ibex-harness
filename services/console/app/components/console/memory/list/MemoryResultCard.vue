<script setup lang="ts">
import { computed } from "vue"
import { Lock, PanelRightOpen } from "@lucide/vue"
import type { PreviewMemory } from "@/lib/memory-preview"
import { memoryDetailHref } from "@/lib/memory-list-query"
import { memoryAgentName, memoryFlags } from "@/lib/memory-list"
import MemoryCategoryChip from "./primitives/MemoryCategoryChip.vue"
import MemoryAgentBadge from "./primitives/MemoryAgentBadge.vue"
import MemoryFlagPill from "./primitives/MemoryFlagPill.vue"
import MemoryStatementText from "./primitives/MemoryStatementText.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import MemoryStatusPill from "@/components/console/memory/primitives/MemoryStatusPill.vue"

const props = defineProps<{
  memory: PreviewMemory
  selected: boolean
  active?: boolean
  query: string
  returnTo: string
}>()

const emit = defineEmits<{
  open: [id: string]
  peek: [id: string]
  toggle: [id: string]
}>()

const flags = computed(() => memoryFlags(props.memory))
const untrusted = computed(() => props.memory.injectionRisk >= 0.5)
const href = computed(() => memoryDetailHref(props.memory.id, props.returnTo))

const edgeClass = computed(() => {
  return "border-l-line-subtle bg-surface-1"
})
</script>

<template>
  <li
    class="ix-memory-card relative rounded-lg border border-line-subtle p-3 transition-colors focus-within:border-line"
    :class="[edgeClass, (selected || active) && 'ring-1 ring-memory/50']"
    :data-memory-card="memory.id"
  >
    <div class="flex items-start gap-2.5">
      <input
        type="checkbox"
        class="mt-0.5 size-3.5 shrink-0 cursor-pointer rounded border-line accent-[var(--ix-memory)]"
        :checked="selected"
        :aria-label="`Select ${memory.id}`"
        @change="emit('toggle', memory.id)"
      >
      <div class="min-w-0 flex-1">
        <NuxtLink
          :to="href"
          class="block text-sm leading-5 text-fg-1"
          :aria-label="`Open ${memory.id}`"
        >
          <MemoryStatementText :text="memory.content" :query="query" :untrusted="untrusted" />
        </NuxtLink>

        <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[0.6875rem] text-fg-3">
          <MemoryCategoryChip :category="memory.category" variant="chip" />
          <MemoryAgentBadge :name="memoryAgentName(memory)" :agent-id="memory.agentId" />
          <span class="font-mono text-[0.625rem]">{{ memory.id }}</span>
        </div>

        <div v-if="memory.tags.length" class="mt-1.5 flex flex-wrap items-center gap-1">
          <span
            v-for="tag in memory.tags.slice(0, 4)"
            :key="tag"
            class="inline-flex h-4 items-center rounded bg-surface-2 px-1.5 font-mono text-[0.625rem] leading-none text-fg-3"
          >
            {{ tag }}
          </span>
        </div>

        <div v-if="memory.status !== 'active' || flags.length" class="mt-2 flex flex-wrap items-center gap-1">
          <MemoryStatusPill v-if="memory.status !== 'active'" :status="memory.status" compact />
          <MemoryFlagPill v-for="flag in flags" :key="flag.kind" :flag="flag" />
        </div>

        <dl class="mt-2.5 grid grid-cols-3 gap-3 border-t border-line-subtle pt-2 text-[0.6875rem]">
          <div class="min-w-0">
            <dt class="text-fg-3">Confidence</dt>
            <dd class="mt-1 flex flex-col gap-1">
              <span class="font-mono text-xs text-fg-2 tabular-nums">{{ memory.confidence.toFixed(2) }}</span>
              <MemoryScoreBar :value="memory.confidence" size="sm" :label="`Confidence ${memory.confidence.toFixed(2)}`" />
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="text-fg-3">Usefulness</dt>
            <dd class="mt-1 flex flex-col gap-1">
              <span class="font-mono text-xs text-fg-2 tabular-nums">{{ memory.usefulness.toFixed(2) }}</span>
              <MemoryScoreBar
                :value="memory.usefulness"
                size="sm"
                color="bg-fg-2"
                :label="`Usefulness ${memory.usefulness.toFixed(2)}`"
              />
            </dd>
          </div>
          <div class="min-w-0">
            <dt class="text-fg-3">Retrievals</dt>
            <dd class="mt-1 truncate font-mono text-xs text-fg-2 tabular-nums">
              {{ memory.retrievalCount > 0 ? memory.retrievalCount : "—" }}
            </dd>
          </div>
        </dl>

        <div class="mt-2 flex items-center justify-between gap-2">
          <span class="truncate font-mono text-[0.6875rem] text-fg-3">Updated {{ memory.updatedLabel }}</span>
          <div class="flex items-center gap-1">
            <button
              type="button"
              class="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[0.6875rem] text-fg-3 transition-colors hover:bg-surface-2 hover:text-fg-1"
              :aria-label="`Peek ${memory.id}`"
              @click="emit('peek', memory.id)"
            >
              <PanelRightOpen :size="12" :stroke-width="1.8" aria-hidden="true" />
              Peek
            </button>
            <button
              type="button"
              disabled
              class="inline-flex h-7 items-center gap-1 rounded-md px-2 text-[0.6875rem] text-fg-off"
              :aria-label="`Pin ${memory.id} unavailable`"
              title="Read-only console. Requires a privileged write contract."
            >
              <Lock :size="11" :stroke-width="1.8" aria-hidden="true" />
              Pin
            </button>
          </div>
        </div>
      </div>
    </div>
  </li>
</template>
