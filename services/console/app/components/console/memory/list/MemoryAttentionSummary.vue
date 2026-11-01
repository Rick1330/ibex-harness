<script setup lang="ts">
import { computed } from "vue"
import { CalendarClock, CheckCircle2, EyeOff, GitBranch, Pin, ShieldAlert } from "@lucide/vue"
import type { PreviewMemory } from "@/lib/memory-preview"
import { memoryLifecycleCounts, memoryNeedsReview } from "@/lib/memory-list"
import type { MemoryView } from "@/lib/memory-list-query"
import MemoryInfoHint from "@/components/console/memory/primitives/MemoryInfoHint.vue"
import MemoryLifecycleBar from "./primitives/MemoryLifecycleBar.vue"

const props = defineProps<{ memories: PreviewMemory[] }>()
const emit = defineEmits<{ selectView: [view: MemoryView] }>()

const reviewCount = computed(() => props.memories.filter(memoryNeedsReview).length)
const conflictCount = computed(() => props.memories.filter((memory) => memory.conflict?.state === "open").length)
const pinnedCount = computed(() => props.memories.filter((memory) => memory.pinned).length)
const neverCount = computed(() => props.memories.filter((memory) => memory.retrievalCount === 0).length)
const expiringCount = computed(() => props.memories.filter((memory) => memory.validity === "expiring").length)
const lifecycle = computed(() => memoryLifecycleCounts(props.memories))
const activeCount = computed(() => lifecycle.value.find((entry) => entry.status === "active")?.count ?? 0)
</script>

<template>
  <section
    class="grid gap-2.5 rounded-lg bg-surface-1 p-2.5 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.35fr)] lg:items-center lg:gap-5"
    aria-label="Memory attention and health"
  >
    <div class="min-w-0">
      <div class="flex items-center gap-1.5">
        <p class="text-[0.6875rem] leading-4 font-semibold text-fg-3">Needs attention</p>
        <MemoryInfoHint label="About needs-attention counts">
          <p class="font-medium text-fg-1">What needs attention</p>
          <p class="mt-1">
            Quarantine, a high prompt-injection score, or an open conflict requires a human decision. A clean row is not a
            safety certification.
          </p>
        </MemoryInfoHint>
      </div>

      <div class="mt-1.5 grid gap-2 sm:grid-cols-2">
        <button
          v-if="reviewCount > 0"
          type="button"
          class="group flex min-h-11 min-w-0 items-center gap-3 rounded-lg border border-line-subtle bg-surface px-3 py-2 text-left transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          @click="emit('selectView', 'review')"
        >
          <ShieldAlert :size="16" :stroke-width="1.8" class="shrink-0 text-warn" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="flex items-baseline gap-2">
              <span class="ix-kpi text-warn">{{ reviewCount }}</span>
              <span class="text-xs font-medium text-fg-1">Needs review</span>
            </span>
          </span>
          <span class="text-xs text-warn opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden="true">→</span>
        </button>
        <div v-else class="flex min-h-11 items-center gap-3 rounded-lg bg-surface-2 px-3 py-2">
          <CheckCircle2 :size="16" :stroke-width="1.8" class="shrink-0 text-ok" aria-hidden="true" />
          <span>
            <span class="block text-xs font-medium text-fg-1">All clear</span>
            <span class="block text-[0.6875rem] leading-4 text-fg-3">No quarantined or conflicting memories</span>
          </span>
        </div>

        <button
          v-if="conflictCount > 0"
          type="button"
          class="group flex min-h-11 min-w-0 items-center gap-3 rounded-lg border border-line-subtle bg-surface px-3 py-2 text-left transition-colors hover:border-line-strong focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
          @click="emit('selectView', 'conflicts')"
        >
          <GitBranch :size="16" :stroke-width="1.8" class="shrink-0 text-crit" aria-hidden="true" />
          <span class="min-w-0 flex-1">
            <span class="flex items-baseline gap-2">
              <span class="ix-kpi text-crit">{{ conflictCount }}</span>
              <span class="text-xs font-medium text-fg-1">Open conflicts</span>
            </span>
          </span>
          <span class="text-xs text-crit opacity-0 transition-opacity group-hover:opacity-100 group-focus-visible:opacity-100" aria-hidden="true">→</span>
        </button>
        <div v-else class="flex min-h-11 items-center gap-3 rounded-lg bg-surface-2 px-3 py-2">
          <CheckCircle2 :size="16" :stroke-width="1.8" class="shrink-0 text-ok" aria-hidden="true" />
          <span>
            <span class="block text-xs font-medium text-fg-1">No open conflicts</span>
            <span class="block text-[0.6875rem] leading-4 text-fg-3">Conflicts resolve only through explicit review</span>
          </span>
        </div>
      </div>
    </div>

    <div class="min-w-0">
      <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 leading-4">
        <div class="flex items-center gap-2">
          <p class="text-[0.6875rem] leading-4 font-semibold text-fg-3">Health</p>
          <p class="text-xs leading-4 text-fg-2">
            Lifecycle
            <span class="ml-1 font-mono text-fg-1 tabular-nums">{{ activeCount }}</span>
            <span class="text-fg-3">active</span>
          </p>
        </div>
        <button
          type="button"
          class="inline-flex items-center gap-1 text-[0.6875rem] text-fg-3 transition-colors hover:text-fg-1"
          @click="emit('selectView', 'tombstoned')"
        >
          Tombstoned
          <span class="font-mono text-fg-2 tabular-nums">{{ lifecycle.find((entry) => entry.status === 'deleted')?.count ?? 0 }}</span>
        </button>
      </div>

      <div class="mt-1.5">
        <MemoryLifecycleBar :counts="lifecycle" :total="memories.length" show-legend />
      </div>

      <div class="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-fg-3">
        <button
          type="button"
          class="inline-flex items-center gap-1 transition-colors hover:text-fg-1"
          @click="emit('selectView', 'never')"
        >
          <EyeOff :size="11" :stroke-width="1.8" aria-hidden="true" />
          Never retrieved
          <span class="font-mono text-fg-2 tabular-nums">{{ neverCount }}</span>
        </button>
        <span class="text-fg-off" aria-hidden="true">·</span>
        <button
          type="button"
          class="inline-flex items-center gap-1 transition-colors hover:text-fg-1"
          @click="emit('selectView', 'expiring')"
        >
          <CalendarClock :size="11" :stroke-width="1.8" aria-hidden="true" />
          Expiring in 30 days
          <span class="font-mono text-fg-2 tabular-nums">{{ expiringCount }}</span>
        </button>
        <span class="text-fg-off" aria-hidden="true">·</span>
        <button
          type="button"
          class="inline-flex items-center gap-1 transition-colors hover:text-fg-1"
          @click="emit('selectView', 'pinned')"
        >
          <Pin :size="11" :stroke-width="1.8" aria-hidden="true" />
          Pinned
          <span class="font-mono text-fg-2 tabular-nums">{{ pinnedCount }}</span>
        </button>
        <MemoryInfoHint label="About health counts">
          <p class="font-medium text-fg-1">How health is counted</p>
          <p class="mt-1">
            Lifecycle uses the stored status. Never retrieved means no retrieval event is recorded. Expiring means the
            valid-until date falls within 30 days of the preview clock.
          </p>
        </MemoryInfoHint>
      </div>
    </div>
  </section>
</template>
