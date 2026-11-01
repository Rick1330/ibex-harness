<script setup lang="ts">
import { computed } from "vue"
import { Archive, Lock, PanelRightOpen, Pin, Trash2 } from "@lucide/vue"
import { MEMORY_SOURCE_LABELS, type PreviewMemory } from "@/lib/memory-preview"
import { getMemoryDetail } from "@/lib/memory-detail-preview"
import {
  memoryDetailHref,
} from "@/lib/memory-list-query"
import { memoryFlags, memoryShortId } from "@/lib/memory-list"
import type { MemoryOptionalColumn } from "@/lib/memory-list-query"
import MemoryCategoryChip from "./primitives/MemoryCategoryChip.vue"
import MemoryAgentBadge from "./primitives/MemoryAgentBadge.vue"
import MemoryScopeChip from "./primitives/MemoryScopeChip.vue"
import MemoryFlagPill from "./primitives/MemoryFlagPill.vue"
import MemorySparkline from "./primitives/MemorySparkline.vue"
import MemoryStatementText from "./primitives/MemoryStatementText.vue"
import MemoryScoreBar from "@/components/console/memory/primitives/MemoryScoreBar.vue"
import MemoryStatusPill from "@/components/console/memory/primitives/MemoryStatusPill.vue"

const props = defineProps<{
  memory: PreviewMemory
  selected: boolean
  active?: boolean
  density: "comfortable" | "compact"
  columns: MemoryOptionalColumn[]
  showTags: boolean
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
const visibleFlags = computed(() => flags.value.slice(0, 2))
const hiddenFlags = computed(() => flags.value.slice(2))
const hiddenFlagCount = computed(() => hiddenFlags.value.length)
const sparkline = computed(() => getMemoryDetail(props.memory.id)?.retrieval.sparkline ?? [])
const href = computed(() => memoryDetailHref(props.memory.id, props.returnTo))

const rowClass = computed(() => {
  if (props.selected) return "bg-accent-tint/40"
  return "hover:bg-raised/60"
})

const statusVisible = computed(() => props.memory.status !== "active")

const retrievalTitle = computed(() =>
  props.memory.retrievalCount === 0
    ? "No retrieval event is recorded. Inclusion is not influence."
    : `${props.memory.retrievalCount} retrievals · last ${props.memory.lastRetrievedLabel}. Inclusion is not influence.`,
)

const updatedTitle = computed(() => `${props.memory.updatedAt.replace("T", " ").replace("Z", " UTC")} · updated`)

function onRowClick(event: MouseEvent): void {
  if (event.target instanceof Element && event.target.closest("a, button, input, label")) return
  emit("open", props.memory.id)
}

function onRowKeydown(event: KeyboardEvent): void {
  if (event.target instanceof Element && event.target.closest("a, button, input")) return
  if (event.key === "Enter") {
    event.preventDefault()
    emit("open", props.memory.id)
  } else if (event.key === " " || event.key === "Spacebar") {
    event.preventDefault()
    emit("peek", props.memory.id)
  } else if (event.key === "x" || event.key === "X") {
    event.preventDefault()
    emit("toggle", props.memory.id)
  }
}
</script>

<template>
  <tr
    class="ix-memory-row group relative border-b border-line-subtle transition-colors focus-visible:outline-none"
    :class="[rowClass, density === 'compact' ? 'h-8' : 'h-11', active && !selected && 'ring-1 ring-accent/35 ring-inset']"
    :data-selected="selected ? 'true' : undefined"
    :data-active="active ? 'true' : undefined"
    :data-memory-row="memory.id"
    tabindex="0"
    :aria-label="`Memory ${memory.id}`"
    @click="onRowClick"
    @keydown="onRowKeydown"
  >
    <td class="w-9 pr-0 pl-2 align-middle">
      <input
        type="checkbox"
        class="size-3.5 cursor-pointer rounded border-line accent-[var(--ix-memory)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        :checked="selected"
        :aria-label="`Select ${memory.id}`"
        @click.stop
        @change="emit('toggle', memory.id)"
      >
    </td>

    <td class="min-w-0 py-1.5 pr-3 pl-1.5 align-middle">
      <div class="flex min-w-0 items-start gap-2">
        <div class="min-w-0 flex-1">
          <NuxtLink
            :to="href"
            class="block min-w-0 truncate text-sm leading-5 text-fg-1 transition-colors hover:text-accent focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
            :aria-label="`Open ${memory.id}`"
            :title="memory.content"
            @click.stop
          >
            <MemoryStatementText :text="memory.content" :query="query" :untrusted="untrusted" />
          </NuxtLink>

          <div
            v-if="density !== 'compact'"
            class="mt-0.5 flex min-w-0 items-center gap-1.5 overflow-hidden text-[0.6875rem] leading-4 text-fg-3"
          >
            <MemoryCategoryChip :category="memory.category" class="shrink-0" />
            <span class="text-fg-off" aria-hidden="true">·</span>
            <MemoryAgentBadge :name="memory.agent" :agent-id="memory.agentId" class="min-w-0" />
            <span class="text-fg-off" aria-hidden="true">·</span>
            <span class="shrink-0 font-mono text-[0.625rem]">{{ memoryShortId(memory.id) }}</span>
            <template v-if="showTags && memory.tags.length">
              <span class="text-fg-off" aria-hidden="true">·</span>
              <span class="flex min-w-0 items-center gap-1 overflow-hidden">
                <span
                  v-for="tag in memory.tags.slice(0, 2)"
                  :key="tag"
                  class="inline-flex h-4 max-w-24 shrink-0 items-center truncate rounded bg-surface-2 px-1.5 font-mono text-[0.625rem] leading-none text-fg-3"
                  :title="`Tag ${tag}`"
                >
                  {{ tag }}
                </span>
                <span v-if="memory.tags.length > 2" class="shrink-0 font-mono text-[0.625rem] text-fg-3">
                  +{{ memory.tags.length - 2 }}
                </span>
              </span>
            </template>
            <span v-if="untrusted" class="shrink-0 rounded bg-warn-tint px-1.5 text-[0.625rem] font-medium text-warn">
              Untrusted text
            </span>
          </div>
        </div>
      </div>
    </td>

    <td class="py-1.5 pr-1 align-middle">
      <div class="flex min-w-0 flex-wrap items-center gap-1">
        <MemoryStatusPill v-if="statusVisible" :status="memory.status" compact class="shrink-0" />
        <MemoryFlagPill v-for="flag in visibleFlags" :key="flag.kind" :flag="flag" />
        <span
          v-if="hiddenFlagCount > 0"
          class="inline-flex h-5 shrink-0 items-center rounded-full border border-line-subtle bg-surface-2 px-1.5 font-mono text-[0.625rem] leading-none text-fg-3"
          :title="hiddenFlags.map((flag) => flag.title).join(' ') || undefined"
          :aria-label="`${hiddenFlagCount} more flags: ${hiddenFlags.map((flag) => flag.label).join(', ')}`"
        >
          +{{ hiddenFlagCount }}
        </span>
      </div>
    </td>

    <td v-if="columns.includes('source')" class="px-2 py-1.5 align-middle">
      <span class="truncate text-xs text-fg-3">{{ MEMORY_SOURCE_LABELS[memory.source] }}</span>
    </td>

    <td v-if="columns.includes('lineage')" class="px-2 py-1.5 align-middle">
      <span v-if="memory.supersededBy || memory.mergedInto" class="font-mono text-[0.6875rem] text-fg-3">
        {{ memory.mergedInto ? `merged → ${memoryShortId(memory.mergedInto)}` : `superseded → ${memoryShortId(memory.supersededBy!)}` }}
      </span>
    </td>

    <td v-if="columns.includes('validity')" class="px-2 py-1.5 align-middle">
      <span
        v-if="memory.validity !== 'open'"
        class="font-mono text-[0.6875rem]"
        :class="memory.validity === 'expired' ? 'text-crit' : 'text-warn'"
      >
        {{ memory.validityLabel }}
      </span>
      <span v-else class="sr-only">Open validity</span>
    </td>

    <td v-if="columns.includes('memoryId')" class="px-2 py-1.5 align-middle">
      <span class="font-mono text-[0.6875rem] text-fg-3">{{ memory.id }}</span>
    </td>

    <td v-if="columns.includes('agentId')" class="px-2 py-1.5 align-middle">
      <span class="font-mono text-[0.6875rem] text-fg-3">{{ memory.agentId }}</span>
    </td>

    <td v-if="columns.includes('sessionId')" class="px-2 py-1.5 align-middle">
      <span v-if="memory.sessionId" class="font-mono text-[0.6875rem] text-fg-3">{{ memory.sessionId }}</span>
    </td>

    <td v-if="columns.includes('visibility')" class="px-2 py-1.5 align-middle">
      <MemoryScopeChip :visibility="memory.visibility" />
    </td>

    <td class="px-2 py-1.5 align-middle">
      <div class="flex min-w-0 flex-col gap-1">
        <span class="font-mono text-xs leading-4 text-fg-2 tabular-nums">{{ memory.confidence.toFixed(2) }}</span>
        <MemoryScoreBar
          :value="memory.confidence"
          size="sm"
          :label="`Confidence ${memory.confidence.toFixed(2)} of 1.00`"
          color="bg-s1"
        />
      </div>
    </td>

    <td class="px-2 py-1.5 align-middle">
      <div class="flex min-w-0 flex-col gap-1">
        <span class="font-mono text-xs leading-4 text-fg-2 tabular-nums">{{ memory.usefulness.toFixed(2) }}</span>
        <MemoryScoreBar
          :value="memory.usefulness"
          size="sm"
          :label="`Usefulness ${memory.usefulness.toFixed(2)} of 1.00`"
          color="bg-s3"
        />
      </div>
    </td>

    <td class="px-2 py-1.5 align-middle">
      <div class="flex min-w-0 items-center gap-2" :title="retrievalTitle">
        <template v-if="memory.retrievalCount > 0">
          <span class="font-mono text-xs leading-4 text-fg-2 tabular-nums">{{ memory.retrievalCount }}</span>
          <MemorySparkline
            :points="sparkline"
            :label="`${memory.retrievalCount} retrievals over the last 14 days`"
            :width="34"
            :height="14"
          />
          <span class="truncate text-[0.6875rem] text-fg-3">{{ memory.lastRetrievedLabel }}</span>
        </template>
        <span v-else class="sr-only">Never retrieved</span>
      </div>
    </td>

    <td class="relative py-1.5 pr-2 pl-2 align-middle">
      <span class="block truncate text-right font-mono text-[0.6875rem] text-fg-3" :title="updatedTitle">
        {{ memory.updatedLabel }}
      </span>

      <div
        class="pointer-events-none absolute inset-y-0 right-1.5 flex items-center gap-0.5 opacity-0 transition-opacity group-hover:pointer-events-auto group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:opacity-100"
      >
        <button
          type="button"
          class="inline-flex size-6 items-center justify-center rounded text-fg-3 transition-colors hover:bg-surface-1 hover:text-fg-1 focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-accent"
          :aria-label="`Peek ${memory.id}`"
          title="Peek (Space)"
          @click.stop="emit('peek', memory.id)"
        >
          <PanelRightOpen :size="13" :stroke-width="1.8" aria-hidden="true" />
        </button>
        <button
          type="button"
          disabled
          class="relative inline-flex size-6 cursor-not-allowed items-center justify-center rounded text-fg-off"
          :aria-label="`Pin ${memory.id} unavailable`"
          title="Read-only console. Requires a privileged write contract."
        >
          <Pin :size="12" :stroke-width="1.8" aria-hidden="true" />
          <Lock :size="7" :stroke-width="2.4" class="absolute" aria-hidden="true" />
        </button>
        <button
          type="button"
          disabled
          class="inline-flex size-6 cursor-not-allowed items-center justify-center rounded text-fg-off"
          :aria-label="`Archive ${memory.id} unavailable`"
          title="Read-only console. Requires a privileged write contract."
        >
          <Archive :size="12" :stroke-width="1.8" aria-hidden="true" />
        </button>
        <button
          type="button"
          disabled
          class="inline-flex size-6 cursor-not-allowed items-center justify-center rounded text-fg-off"
          :aria-label="`Delete ${memory.id} unavailable`"
          title="Read-only console. Requires a privileged write contract."
        >
          <Trash2 :size="12" :stroke-width="1.8" aria-hidden="true" />
        </button>
      </div>
    </td>
  </tr>
</template>

<style scoped>
.ix-memory-row:focus-visible {
  outline: 2px solid var(--ix-memory);
  outline-offset: -2px;
}
</style>
